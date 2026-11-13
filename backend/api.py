"""API local do Atlas Studio. Nao exponha diretamente na internet."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4
from time import perf_counter

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from atlas_agent import AtlasError, Context, executar_pedido, MODEL
from atlas_pipeline import ResultadoPipeline, executar_pipeline
from dashboard_data import preparar_painel
from relatorio_v5 import texto_relatorio
from data_analysis import MAX_UPLOAD_BYTES, read_dataset, analyze_dataframe, DatasetError
from dataset_agent import ask_dataset, QueryError
import pandas as pd
from backend.auth_store import Actor, require_actor, settings, insert_run, insert_messages, list_runs, list_messages, read_run
from backend import research, model_lab

app = FastAPI(title="Atlas Agent Studio API", version="12.0.0", docs_url="/docs")
# Apenas dev local. Produção exige autenticação, TLS e politicas de acesso.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

@dataclass
class Session:
    context: Context
    last_result: ResultadoPipeline | None
    updated: datetime
    user_id: str = "local"
    dataset_summary: dict | None = None
    dataset_frame: pd.DataFrame | None = None

# Sessões em memória: desenvolvimento local, sem persistência, limite e TTL.
_SESSIONS: OrderedDict[str, Session] = OrderedDict()
_LOCK = RLock()
MAX_SESSIONS = 8
SESSION_TTL = timedelta(hours=2)


def session_for(key: str | None, user_id: str = "local") -> tuple[str, Session]:
    now = datetime.now(timezone.utc)
    with _LOCK:
        for token in list(_SESSIONS):
            if now - _SESSIONS[token].updated > SESSION_TTL:
                del _SESSIONS[token]
        if key and key in _SESSIONS:
            existing = _SESSIONS[key]
            if existing.user_id != user_id:
                raise HTTPException(403, "Sessão pertence a outra conta.")
            existing.updated = now
            _SESSIONS.move_to_end(key)
            return key, existing
        if key is not None:
            raise HTTPException(404, "Sessao desconhecida ou expirada. Inicie uma nova sessao.")
        token = uuid4().hex
        _SESSIONS[token] = Session(Context(), None, now, user_id)
        while len(_SESSIONS) > MAX_SESSIONS:
            _SESSIONS.popitem(last=False)
        return token, _SESSIONS[token]


class SessionBody(BaseModel):
    session_id: str = Field(min_length=32, max_length=32)


class AnalyzeBody(SessionBody):
    meses: int = Field(default=60, ge=36, le=120)
    horizonte: int = Field(default=3, ge=1, le=6)


class ChatBody(SessionBody):
    pergunta: str = Field(min_length=1, max_length=1000)
    rapido: bool = True


@app.get('/api/health')
def health():
    configured = settings() is not None
    return {'status': 'ok', 'version': '12.0.0', 'modelo': MODEL,
            'scope': 'local_com_supabase' if configured else 'local',
            'authenticated': configured, 'persistence': configured}


@app.post('/api/session')
def create_session(actor: Actor = Depends(require_actor)):
    token, session = session_for(None, actor.user_id)
    if actor.remote:
        saved = [m for m in list_messages(actor, 24) if m['channel'] == 'assistente']
        session.context.historico = [
            {'role': m['role'], 'content': m['body']}
            for m in saved[-18:] if m['role'] in ('user', 'assistant')
        ]
    return {'session_id': token}


@app.post('/api/session/clear')
def clear_session(body: SessionBody, actor: Actor = Depends(require_actor)):
    _, session = session_for(body.session_id, actor.user_id)
    session.context = Context()
    session.last_result = None
    session.dataset_summary = None
    session.dataset_frame = None
    return {'ok': True}


@app.post('/api/analyze')
def analyze(body: AnalyzeBody, actor: Actor = Depends(require_actor)):
    _, session = session_for(body.session_id, actor.user_id)
    try:
        result = executar_pipeline(session.context, body.meses, body.horizonte)
        panel = preparar_painel(result, session.context.ipca_rows or [])
    except (AtlasError, ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    insert_run(actor, 'economia', f'IPCA {body.meses} meses / horizonte {body.horizonte}',
               f"Modelo {panel['indicadores']['modelo']} — {panel['indicadores']['ultima_competencia']}",
               {'painel': panel, 'verificacao': result.verificacao})
    session.last_result = result
    return {'session_id': body.session_id, 'painel': panel,
            'verificacao': result.verificacao}


@app.post('/api/chat')
def chat(body: ChatBody, actor: Actor = Depends(require_actor)):
    _, session = session_for(body.session_id, actor.user_id)
    started = perf_counter()
    try:
        resposta, ferramentas = executar_pedido(body.pergunta, ctx=session.context, rapido=body.rapido)
    except (AtlasError, ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    insert_messages(actor, 'assistente', body.pergunta, resposta, ferramentas)
    return {'resposta': resposta, 'ferramentas': ferramentas,
            'duracao_segundos': round(perf_counter() - started, 2),
            'modo_rapido': body.rapido}


@app.post('/api/report')
def report(body: SessionBody, actor: Actor = Depends(require_actor)):
    _, session = session_for(body.session_id, actor.user_id)
    if session.last_result is None:
        raise HTTPException(409, 'Execute uma analise antes de gerar o relatorio.')
    try:
        content = texto_relatorio(session.last_result)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    filename = f'atlas_relatorio_{session.context.run_id}.md'
    insert_run(actor, 'relatorio', filename, 'Relatório econômico em Markdown',
               {'markdown': content, 'filename': filename})
    return {'filename': filename, 'markdown': content}


@app.post('/api/data/upload')
async def upload_data(session_id: str = Form(...), file: UploadFile = File(...),
                      actor: Actor = Depends(require_actor)):
    _, session = session_for(session_id, actor.user_id)
    if not file.filename:
        raise HTTPException(422, 'Nome do arquivo ausente.')
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        frame = read_dataset(file.filename, content)
        # Limita a ocupacao de RAM das sessoes locais simultaneas.
        if int(frame.memory_usage(index=True, deep=True).sum()) > 40 * 1024 * 1024:
            raise DatasetError('Planilha excede 40 MB de uso estimado na memoria.')
        summary = analyze_dataframe(frame, file.filename)
    except DatasetError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()
    # Persistimos somente metadados/indicadores agregados, jamais amostras de linhas.
    safe_summary = {k: summary.get(k) for k in ('arquivo', 'linhas', 'colunas_total', 'celulas_ausentes', 'linhas_duplicadas')}
    insert_run(actor, 'dataset', f"Planilha: {summary.get('arquivo', 'arquivo')}",
               f"{summary['linhas']} linhas, {summary['colunas_total']} colunas",
               {'resumo': safe_summary, 'arquivo_descartado': True})
    session.dataset_summary = summary
    session.dataset_frame = frame
    return {'resumo': summary, 'armazenamento': 'memoria da sessao; arquivo original descartado'}


@app.post('/api/data/summary')
def data_summary(body: SessionBody, actor: Actor = Depends(require_actor)):
    _, session = session_for(body.session_id, actor.user_id)
    if session.dataset_summary is None:
        raise HTTPException(404, 'Nenhuma planilha analisada nesta sessao.')
    return {'resumo': session.dataset_summary}


@app.post('/api/data/ask')
def ask_data(body: ChatBody, actor: Actor = Depends(require_actor)):
    _, session = session_for(body.session_id, actor.user_id)
    if session.dataset_frame is None:
        raise HTTPException(409, 'Envie uma planilha na aba Atlas Data antes de perguntar.')
    try:
        answer, tools = ask_dataset(session.dataset_frame, body.pergunta)
    except (QueryError, ValueError, AtlasError) as exc:
        raise HTTPException(422, str(exc)) from exc
    insert_messages(actor, 'dados', body.pergunta, answer, tools)
    return {'resposta': answer, 'ferramentas': tools}


@app.get('/api/history')
def history(actor: Actor = Depends(require_actor)):
    return {'runs': list_runs(actor), 'remote': actor.remote}


@app.get('/api/messages')
def messages(actor: Actor = Depends(require_actor)):
    return {'messages': list_messages(actor), 'remote': actor.remote}


class ReadRunBody(BaseModel):
    run_id: str


@app.post('/api/history/read')
def history_read(body: ReadRunBody, actor: Actor = Depends(require_actor)):
    entry = read_run(actor, body.run_id)
    if entry is None:
        raise HTTPException(404, 'Registro não encontrado ou sem autorização.')
    return {'run': entry}


# v10: Pesquisa documental RAG. Todos os endpoints exigem identidade validada.
class ResearchQuestion(BaseModel):
    pergunta: str = Field(min_length=4, max_length=1000)
    document_id: str | None = None

class ResearchDelete(BaseModel):
    document_id: str


@app.get('/api/research/documents')
def research_documents(actor: Actor = Depends(require_actor)):
    return {'documents': research.list_documents(actor)}


@app.post('/api/research/upload')
async def research_upload(file: UploadFile = File(...), actor: Actor = Depends(require_actor)):
    if not actor.remote:
        raise HTTPException(409, 'Pesquisa documental exige login Supabase.')
    if not file.filename:
        raise HTTPException(422, 'Arquivo sem nome.')
    try:
        body = await file.read(research.MAX_UPLOAD_BYTES + 1)
        result = research.store_document(actor, file.filename, body)
        return {'document': result, 'aviso': 'Texto extraido e embeddings armazenados no Supabase; arquivo original descartado.'}
    except research.ResearchError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()


@app.post('/api/research/ask')
def research_ask(body: ResearchQuestion, actor: Actor = Depends(require_actor)):
    if not actor.remote:
        raise HTTPException(409, 'Pesquisa documental exige login Supabase.')
    try:
        result = research.answer_question(actor, body.pergunta, body.document_id)
    except research.ResearchError as exc:
        raise HTTPException(422, str(exc)) from exc
    insert_messages(actor, 'research', body.pergunta, result['resposta'], [])
    return result


@app.post('/api/research/delete')
def research_delete(body: ResearchDelete, actor: Actor = Depends(require_actor)):
    try:
        research.delete_document(actor, body.document_id)
    except research.ResearchError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'ok': True}


# v11: Laboratório de modelos locais. Nenhum resultado é gravado no Supabase.
class LabBenchmarkBody(BaseModel):
    models: list[str] = Field(min_length=1, max_length=2)
    repetitions: int = Field(default=1, ge=1, le=2)


@app.get('/api/lab/models')
def lab_models(actor: Actor = Depends(require_actor)):
    try:
        return {'models': model_lab.list_models(), 'running': model_lab.running_models()}
    except model_lab.ModelLabError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post('/api/lab/benchmark')
def lab_benchmark(body: LabBenchmarkBody, actor: Actor = Depends(require_actor)):
    try:
        return model_lab.run_benchmark(body.models, body.repetitions)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except model_lab.ModelLabError as exc:
        raise HTTPException(503, str(exc)) from exc
