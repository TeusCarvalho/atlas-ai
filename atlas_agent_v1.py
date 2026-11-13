"""Atlas Agent MVP: local Ollama tool calling with a strict tool allowlist."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

OLLAMA_URL = 'http://127.0.0.1:11434/api/chat'
MODEL = 'qwen3:4b-instruct'
LOGGER = logging.getLogger('atlas_agent')

TOOL_SCHEMA = {
    'type': 'function',
    'function': {
        'name': 'calcular_variacao_percentual',
        'description': 'Calcula a variacao percentual de um valor inicial para um valor final, com precisao decimal.',
        'parameters': {
            'type': 'object',
            'properties': {
                'valor_inicial': {'type': 'number', 'description': 'Valor inicial da comparacao'},
                'valor_final': {'type': 'number', 'description': 'Valor final da comparacao'},
            },
            'required': ['valor_inicial', 'valor_final'],
            'additionalProperties': False,
        },
    },
}

SYSTEM_PROMPT = (
    'Voce e o Atlas Agent, assistente de automacao em portugues brasileiro. '
    'Quando o usuario pedir uma variacao percentual entre dois valores, use obrigatoriamente '
    'a ferramenta calcular_variacao_percentual. Nao invente valores. '
    'Depois de receber o resultado da ferramenta, responda de maneira curta em portugues. '
    'Nao exponha raciocinio interno.'
)


class AtlasError(Exception):
    pass


def calcular_variacao_percentual(valor_inicial: int | float | str, valor_final: int | float | str) -> dict[str, Any]:
    try:
        inicial = Decimal(str(valor_inicial))
        final = Decimal(str(valor_final))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Os valores devem ser numericos.') from exc
    if not inicial.is_finite() or not final.is_finite():
        raise ValueError('Os valores devem ser finitos.')
    if inicial == 0:
        raise ValueError('O valor inicial nao pode ser zero.')
    variacao = (final - inicial) / abs(inicial) * Decimal('100')
    return {
        'valor_inicial': str(inicial),
        'valor_final': str(final),
        'variacao_percentual': str(variacao.quantize(Decimal('0.01'))),
        'interpretacao': 'aumento' if variacao > 0 else 'queda' if variacao < 0 else 'sem_variacao',
    }


ALLOWLIST = {'calcular_variacao_percentual': calcular_variacao_percentual}


def pedir_ollama(messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'model': MODEL, 'messages': messages, 'stream': False,
        'options': {'temperature': 0.1, 'num_predict': 400},
    }
    if tools is not None:
        payload['tools'] = tools
    # This model variant is instructed directly; don't include `think` in the API payload.
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=(5, 120))
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise AtlasError(f'Falha na comunicacao com o Ollama: {exc}') from exc
    if not isinstance(data, dict) or not isinstance(data.get('message'), dict):
        raise AtlasError('Resposta inesperada da API Ollama.')
    LOGGER.info('Ollama: motivo=%s tokens=%s', data.get('done_reason'), data.get('eval_count'))
    return data


def executar_pedido(pergunta: str) -> tuple[str, list[dict[str, Any]]]:
    messages: list[dict[str, Any]] = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': pergunta},
    ]
    first = pedir_ollama(messages, tools=[TOOL_SCHEMA])
    reply = first['message']
    calls = reply.get('tool_calls') or []
    if not calls:
        return str(reply.get('content') or 'O modelo nao retornou uma resposta.'), []
    if not isinstance(calls, list) or len(calls) > 3:
        raise AtlasError('Numero de ferramentas solicitado acima do limite.')

    # Keep the assistant's tool calls in the conversation for the follow-up.
    messages.append(reply)
    executed: list[dict[str, Any]] = []
    for call in calls:
        function = call.get('function') or {}
        name = function.get('name')
        if name not in ALLOWLIST:
            raise AtlasError(f'Ferramenta nao autorizada: {name!r}')
        args = function.get('arguments', {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError as exc:
                raise AtlasError('Argumentos JSON invalidos.') from exc
        if not isinstance(args, dict) or set(args) != {'valor_inicial', 'valor_final'}:
            raise AtlasError('Parametros de ferramenta invalidos.')
        try:
            result = ALLOWLIST[name](**args)
        except (ValueError, TypeError) as exc:
            result = {'erro': str(exc)}
        executed.append({'ferramenta': name, 'argumentos': args, 'resultado': result})
        messages.append({'role': 'tool', 'tool_name': name, 'content': json.dumps(result, ensure_ascii=False)})
    final = pedir_ollama(messages)
    return str(final['message'].get('content') or 'Sem resposta final.'), executed


def main() -> None:
    print('ATLAS AGENT - Teste de ferramentas com Ollama local')
    print(f'Modelo: {MODEL} | Digite sair para encerrar.\n')
    while True:
        try:
            question = input('Voce > ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nEncerrado.')
            return
        if question.lower() in {'sair', 'exit', 'quit'}:
            return
        if not question:
            continue
        try:
            answer, executed = executar_pedido(question)
        except AtlasError as exc:
            print(f'Erro: {exc}\n')
            continue
        for item in executed:
            print(f'Ferramenta usada: {item["ferramenta"]}')
            print(f'Resultado Python: {json.dumps(item["resultado"], ensure_ascii=False)}')
        print(f'Atlas > {answer}\n')


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()
