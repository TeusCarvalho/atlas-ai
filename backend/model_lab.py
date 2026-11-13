"""Atlas Model Lab: benchmarks locais pequenos e reproduzíveis com Ollama.

Não baixa modelos, não executa ferramentas e não grava prompts ou resultados
no Supabase. Os testes verificam requisitos específicos, não inteligência geral.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict
from statistics import mean
from time import perf_counter
from typing import Any

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"
MAX_MODELS = 2
MAX_REPETITIONS = 2


class ModelLabError(Exception):
    """Erro sem exposição de detalhes internos ou credenciais."""


def _clean(text: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(ch))


def _json_request(method: str, path: str, *, payload: dict | None = None, timeout: float = 12.0) -> dict:
    """Somente caminhos controlados em servidor Ollama fixo no loopback."""
    if path not in {"/api/tags", "/api/chat", "/api/ps"}:
        raise ValueError('Endpoint do Ollama não autorizado.')
    try:
        if method == 'GET':
            response = httpx.get(OLLAMA_URL + path, timeout=timeout)
        elif method == 'POST':
            response = httpx.post(OLLAMA_URL + path, json=payload, timeout=timeout)
        else:
            raise ValueError('Método não autorizado.')
    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
        raise ModelLabError('Ollama indisponível ou sem resposta. Verifique se o aplicativo está aberto.') from exc
    except httpx.RequestError as exc:
        raise ModelLabError('Não foi possível comunicar com o Ollama local.') from exc
    if response.status_code >= 400:
        raise ModelLabError(f'Ollama retornou HTTP {response.status_code}; verifique se o modelo suporta chat e ferramentas.')
    try:
        data = response.json()
    except ValueError as exc:
        raise ModelLabError('Ollama devolveu uma resposta inválida.') from exc
    if not isinstance(data, dict):
        raise ModelLabError('Formato de resposta inválido do Ollama.')
    return data


def list_models() -> list[dict]:
    """Enumera modelos instalados; não faz download ou instalação."""
    response = _json_request('GET', '/api/tags')
    models = response.get('models', [])
    if not isinstance(models, list):
        raise ModelLabError('Lista de modelos do Ollama é inválida.')
    available: dict[str, dict] = {}
    for entry in models:
        if not isinstance(entry, dict):
            continue
        name = entry.get('name') or entry.get('model')
        # O /api/tags não fornece capacidades completas. Excluímos nomes
        # explicitamente de embedding, mas o teste ainda pode detectar um
        # modelo sem suporte a chat ou ferramentas.
        if not isinstance(name, str) or len(name) > 180 or not name or 'embed' in name.lower():
            continue
        size = entry.get('size', 0)
        if not isinstance(size, (int, float)) or size < 0:
            size = 0
        available[name] = {'name': name, 'size_gb': round(size / 1e9, 2)}
    return sorted(available.values(), key=lambda r: r['name'].lower())


def running_models() -> list[dict]:
    response = _json_request('GET', '/api/ps')
    rows = response.get('models', [])
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        n = row.get('name') or row.get('model')
        if isinstance(n, str):
            vram = row.get('size_vram')
            result.append({'name': n, 'size_vram_gb': round(vram / 1e9, 2) if isinstance(vram, (int, float)) and vram >= 0 else None})
    return result


TOOL_SPEC = {
    'type': 'function',
    'function': {
        'name': 'calcular_variacao_percentual',
        'description': 'Calcula a variação percentual entre dois números.',
        'parameters': {
            'type': 'object',
            'properties': {
                'valor_inicial': {'type': 'number'},
                'valor_final': {'type': 'number'},
            },
            'required': ['valor_inicial', 'valor_final'],
        },
    },
}

SCENARIOS = [
    {
        'id': 'instrucao',
        'title': 'Seguir instrução',
        'description': 'Responde exatamente uma palavra solicitada.',
        'messages': [
            {'role': 'system', 'content': 'Siga o formato solicitado sem explicações.'},
            {'role': 'user', 'content': 'Responda apenas com a palavra ATLAS. Não escreva mais nada.'},
        ],
    },
    {
        'id': 'ferramenta',
        'title': 'Tool calling',
        'description': 'Seleciona a função Python e parâmetros corretos; não executa a função.',
        'messages': [
            {'role': 'system', 'content': 'Use uma das ferramentas disponibilizadas para cálculos.'},
            {'role': 'user', 'content': 'Use a ferramenta calcular_variacao_percentual de 120 para 150.'},
        ],
        'tools': [TOOL_SPEC],
    },
    {
        'id': 'contexto',
        'title': 'Fidelidade ao contexto',
        'description': 'Responde a partir de um trecho fornecido e cita a fonte (RAG simulado).',
        'messages': [
            {'role': 'system', 'content': 'Responda apenas com a fonte indicada. Cite [Fonte 1] e não invente.'},
            {'role': 'user', 'content': (
                'Fonte 1 — Manual fictício: Um veículo só pode ser liberado após registro da conferência '
                'e assinatura digital do encarregado.\n'
                'Pergunta: Qual assinatura é necessária para liberar o veículo? Cite a fonte.'
            )},
        ],
    },
    {
        'id': 'abstencao',
        'title': 'Admitir falta de evidência',
        'description': 'Evita inventar valor não presente no trecho fornecido.',
        'messages': [
            {'role': 'system', 'content': 'Use somente as informações da fonte. Se não houver resposta, diga que a informação não consta.'},
            {'role': 'user', 'content': (
                'Fonte 1 — Manual fictício: Um veículo só pode ser liberado após registro da conferência '
                'e assinatura digital do encarregado. A fonte não contém valores de combustíveis.\n'
                'Pergunta: Qual é o preço do diesel, segundo a fonte?'
            )},
        ],
    },
]


def _arguments(payload: Any) -> dict:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def check_response(scenario_id: str, message: dict) -> tuple[bool, str]:
    """Critérios transparentes e limitados; não equivalem a um juiz de LLM."""
    content = str(message.get('content') or '').strip()
    plain = _clean(content)
    if scenario_id == 'instrucao':
        passed = content.upper() == 'ATLAS'
        return passed, 'Resposta deve ser exatamente ATLAS.'
    if scenario_id == 'ferramenta':
        calls = message.get('tool_calls') or []
        if not isinstance(calls, list):
            calls = []
        for call in calls:
            fn = call.get('function') if isinstance(call, dict) else None
            if not isinstance(fn, dict):
                continue
            args = _arguments(fn.get('arguments'))
            if fn.get('name') != 'calcular_variacao_percentual':
                continue
            try:
                a, b = float(args['valor_inicial']), float(args['valor_final'])
                if math.isfinite(a) and math.isfinite(b) and a == 120 and b == 150:
                    return True, 'Ferramenta e parâmetros corretos.'
            except (ValueError, TypeError, KeyError):
                pass
        return False, 'O modelo precisa solicitar a ferramenta com argumentos 120 e 150.'
    if scenario_id == 'contexto':
        return ('assinatura digital' in plain and 'encarregado' in plain and '[fonte 1]' in plain,
                'Deve citar a assinatura digital do encarregado e [Fonte 1].')
    if scenario_id == 'abstencao':
        refusal = bool(re.search(r'\bnao\b', plain)) and any(
            word in plain for word in ('informa', 'consta', 'menciona', 'especifica', 'disponivel', 'dados', 'valor')
        )
        invented_price = bool(re.search(r'r\s*\$\s*\d|\d+(?:[.,]\d+)?\s*reais\b', plain))
        return refusal and not invented_price, 'Deve dizer que a fonte não informa o preço, sem inventar valores.'
    raise ValueError('Cenário desconhecido.')


def _nanoseconds(data: dict, key: str) -> float:
    value = data.get(key, 0)
    return (value / 1e9) if isinstance(value, (int, float)) and value >= 0 else 0.0


def run_benchmark(model_names: list[str], repetitions: int = 1) -> dict:
    if not isinstance(model_names, list) or not 1 <= len(model_names) <= MAX_MODELS:
        raise ValueError('Selecione um ou dois modelos instalados.')
    if not isinstance(repetitions, int) or not 1 <= repetitions <= MAX_REPETITIONS:
        raise ValueError('Selecione uma ou duas repetições.')
    if len(set(model_names)) != len(model_names):
        raise ValueError('Escolha modelos diferentes para comparar.')

    installed = {item['name'] for item in list_models()}
    if any(name not in installed for name in model_names):
        raise ValueError('Modelo não encontrado na instalação local ou não adequado para chat.')

    results: list[dict] = []
    for model in model_names:  # sequencial: evita concorrência na VRAM de 8 GB
        for repeat in range(repetitions):
            for case in SCENARIOS:
                body = {
                    'model': model,
                    'messages': case['messages'],
                    'stream': False,
                    'think': False,
                    'keep_alive': '1m',
                    'options': {'temperature': 0, 'num_predict': 160},
                }
                if case.get('tools'):
                    body['tools'] = case['tools']
                before = perf_counter()
                try:
                    response = _json_request('POST', '/api/chat', payload=body, timeout=75.0)
                    elapsed = perf_counter() - before
                    msg = response.get('message') or {}
                    if not isinstance(msg, dict):
                        msg = {}
                    passed, criterion = check_response(case['id'], msg)
                    reason = str(response.get('done_reason') or '')
                    passed = passed and reason in ('stop', '')
                    eval_ns = _nanoseconds(response, 'eval_duration')
                    count = response.get('eval_count', 0)
                    count = count if isinstance(count, int) and count >= 0 else 0
                    speed = round(count / eval_ns, 2) if eval_ns > 0 else None
                    results.append({
                        'model': model, 'scenario': case['id'], 'scenario_name': case['title'],
                        'repetition': repeat + 1, 'passed': passed,
                        'criterion': criterion, 'done_reason': reason,
                        'duration_s': round(elapsed, 2),
                        'ollama_duration_s': round(_nanoseconds(response, 'total_duration'), 2),
                        'load_duration_s': round(_nanoseconds(response, 'load_duration'), 2),
                        'output_tokens': count,
                        'prompt_tokens': response.get('prompt_eval_count') if isinstance(response.get('prompt_eval_count'), int) else None,
                        'tokens_per_second': speed,
                        'response_preview': str(msg.get('content') or '')[:550],
                        'tool_calls': [str(c.get('function', {}).get('name')) for c in (msg.get('tool_calls') or [])
                                       if isinstance(c, dict) and isinstance(c.get('function'), dict)][:4],
                        'error': None,
                    })
                except ModelLabError as exc:
                    # Erro isolado por cenário: apresenta o problema, nunca conta como sucesso.
                    results.append({
                        'model': model, 'scenario': case['id'], 'scenario_name': case['title'],
                        'repetition': repeat + 1, 'passed': False, 'criterion': 'Teste não concluído.',
                        'done_reason': 'error', 'duration_s': round(perf_counter() - before, 2),
                        'ollama_duration_s': None, 'load_duration_s': None,
                        'output_tokens': 0, 'prompt_tokens': None, 'tokens_per_second': None,
                        'response_preview': '', 'tool_calls': [], 'error': str(exc),
                    })

    grouped: dict[str, list] = defaultdict(list)
    for row in results:
        grouped[row['model']].append(row)
    summary: list[dict] = []
    for model, rows in grouped.items():
        successful = [r for r in rows if r['done_reason'] != 'error']
        measured_speed = [r['tokens_per_second'] for r in successful if r['tokens_per_second'] is not None]
        summary.append({
            'model': model,
            'checks_passed': sum(bool(r['passed']) for r in rows),
            'checks_total': len(rows),
            'score_percent': round(100 * sum(bool(r['passed']) for r in rows) / len(rows), 1),
            'average_duration_s': round(mean(r['duration_s'] for r in successful), 2) if successful else None,
            'average_tps': round(mean(measured_speed), 2) if measured_speed else None,
            'errors': len(rows) - len(successful),
        })
    return {
        'summary': summary,
        'results': results,
        'repetitions': repetitions,
        'scenarios': [{'id': x['id'], 'name': x['title'], 'description': x['description']} for x in SCENARIOS],
        'notes': [
            'Pontuação indica apenas aprovação nos quatro cenários controlados; não mede inteligência geral.',
            'O cenário de contexto simula RAG com texto fornecido; não testa a recuperação pgvector.',
            'Tokens/s é calculado a partir de eval_count/eval_duration do Ollama; tempo total inclui rede local e carga.',
            'Resultados são mantidos somente no navegador nesta versão; nenhuma pergunta ou benchmark é salvo no Supabase.',
        ],
    }
