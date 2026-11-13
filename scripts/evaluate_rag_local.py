r"""Benchmark real do Ollama local, sem Supabase ou JWT.

Executa os embeddings no Ollama e a geração via backend.research.answer_question.
Apenas a recuperação pgvector é substituída por ranking cosseno em memória.
Comando: .\.venv\Scripts\python.exe scripts\evaluate_rag_local.py
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.auth_store import Actor
from backend import research, rag_eval

DOC_ID = str(UUID(int=1))
ACTOR = Actor(str(UUID(int=2)), None, False)


def synthetic_sections(markdown: str) -> list[tuple[str, str]]:
    """Em arquivos MD reais, páginas são tratadas de modo diferente.

    Este recorte por seção é exclusivo do benchmark e deve ser interpretado
    como teste de componentes, não medição do pgvector em produção.
    """
    result = []
    title = 'Introdução'
    lines = []
    for line in markdown.splitlines():
        if line.startswith('## '):
            if any(x.strip() for x in lines):
                result.append((title, '\n'.join(lines)))
            title, lines = line[3:].strip(), []
        else:
            lines.append(line)
    if any(x.strip() for x in lines):
        result.append((title, '\n'.join(lines)))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Avaliação local do Atlas Deep Research')
    parser.add_argument('--output', default='relatorios/avaliacao_rag_local.json')
    parser.add_argument('--top-k', type=int, default=3, choices=range(1, 9))
    args = parser.parse_args()

    manual = ROOT / 'exemplos' / 'manual_operacional_rag.md'
    cases = json.loads((ROOT / 'evals' / 'rag_cases.json').read_text(encoding='utf-8'))
    if not cases or any(not isinstance(c.get('question'), str) for c in cases):
        raise ValueError('Casos inválidos de avaliação.')

    # Usa as mesmas validações de arquivo da ingestão real.
    research.extract_pages(manual.name, manual.read_bytes())
    sections = synthetic_sections(manual.read_text(encoding='utf-8-sig'))
    chunks = []
    for title, content in sections:
        for chunk in research.split_chunks([(1, title + '\n' + content)]):
            chunks.append({**chunk, 'document_id': DOC_ID,
                           'filename': manual.name, 'section': title})

    vectors = []
    for i in range(0, len(chunks), 12):
        vectors.extend(research.embed_batch([c['content'] for c in chunks[i:i + 12]]))
    print(f'Corpus fictício: {len(sections)} seções, {len(chunks)} trechos; {len(cases)} perguntas.')

    results = []
    for case in cases:
        started = perf_counter()
        try:
            query_vec = research.embed_batch([case['question']])[0]
            retrieved = rag_eval.rank_chunks(query_vec, chunks, vectors, args.top_k,
                                             research.MATCH_THRESHOLD)
            # Usa a função de resposta REAL, mas fornece fontes recuperadas
            # localmente para NÃO acessar o banco Supabase.
            with patch.object(research, 'retrieve', return_value=retrieved):
                answer = research.answer_question(ACTOR, case['question'])
            scored = rag_eval.score_case(case, retrieved, answer)
        except (research.ResearchError, ValueError, OSError) as exc:
            scored = {
                'id': case['id'], 'question': case['question'],
                'expected_behavior': 'answer_with_evidence' if case['answerable'] else 'abstain',
                'retrieval_evidence_coverage': None, 'answer_phrase_coverage': None,
                'valid_citation_in_body': None, 'abstained_heuristic': False,
                'passed_heuristic': False, 'retrieved_chunks': 0, 'answer': '',
                'sources': [], 'error': str(exc),
            }
        scored['duration_seconds'] = round(perf_counter() - started, 2)
        results.append(scored)
        print(f"[{'OK' if scored['passed_heuristic'] else 'REVISAR'}] {case['id']} ({scored['duration_seconds']} s)")

    summary = rag_eval.summarize(results)
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'model': research.os.environ.get('ATLAS_MODEL', 'qwen3:4b-instruct'),
        'embedding_model': research.EMBEDDING_MODEL,
        'method': 'local_ollama_cosine_section_chunks_not_supabase_pgvector',
        'limits': 'Comparações textuais heurísticas; revisar respostas manualmente.',
        'summary': summary, 'cases': results,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Resumo: {summary['passed']}/{summary['cases']} critérios heurísticos aprovados")
    print(f'Relatório: {output}')
    return 0 if summary['passed'] == summary['cases'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
