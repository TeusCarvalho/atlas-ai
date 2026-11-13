"""Aceleracao da v9.2 sem sacrificar contratos de ferramentas e historico."""
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import atlas_agent as atlas
from backend.api import app


def test_ollama_keep_alive_e_limite_curto():
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {'message': {'role': 'assistant', 'content': 'ok'}, 'done_reason': 'stop'}
    with patch('atlas_agent.requests.post', return_value=mock_response) as post:
        data = atlas.pedir_ollama([{'role': 'user', 'content': 'oi'}], max_tokens=256)
    assert data['message']['content'] == 'ok'
    payload = post.call_args.kwargs['json']
    assert payload['keep_alive'] == '15m'
    assert payload['options']['num_predict'] == 256
    assert payload['stream'] is False


def test_modo_rapido_calculo_faz_uma_chamada_ollama(monkeypatch, tmp_path):
    monkeypatch.setattr(atlas, 'LOG_DIR', tmp_path)
    step = {'message': {'role': 'assistant', 'content': '', 'tool_calls': [
        {'function': {'name': 'calcular_variacao_percentual',
                      'arguments': {'valor_inicial': 250, 'valor_final': 400}}}
    ]}}
    ctx = atlas.Context()
    with patch('atlas_agent.pedir_ollama', return_value=step) as model:
        text, tools = atlas.executar_pedido('Calcule a variacao de 250 para 400', ctx=ctx, rapido=True)
    assert '60.00%' in text
    assert len(tools) == 1
    assert tools[0]['resultado']['variacao_percentual'] == '60.00'
    assert model.call_count == 1
    assert model.call_args.kwargs['max_tokens'] == 320
    assert ctx.historico[-1]['role'] == 'assistant'
    assert '60.00%' in ctx.historico[-1]['content']
    assert (tmp_path / 'execucoes.jsonl').exists()


def test_resposta_normal_usa_explicaçao_do_modelo(monkeypatch, tmp_path):
    monkeypatch.setattr(atlas, 'LOG_DIR', tmp_path)
    first = {'message': {'role': 'assistant', 'content': '', 'tool_calls': [
        {'function': {'name': 'calcular_variacao_percentual',
                      'arguments': {'valor_inicial': 120, 'valor_final': 150}}}
    ]}}
    last = {'message': {'role': 'assistant', 'content': 'Resposta explicada pelo modelo.'}}
    with patch('atlas_agent.pedir_ollama', side_effect=[first, last]) as model:
        text, tools = atlas.executar_pedido('Calcule de 120 para 150', rapido=False)
    assert text == 'Resposta explicada pelo modelo.'
    assert len(tools) == 1
    assert model.call_count == 2


def test_modo_rapido_nao_disfarca_falhas_na_ferramenta(monkeypatch, tmp_path):
    monkeypatch.setattr(atlas, 'LOG_DIR', tmp_path)
    first = {'message': {'role': 'assistant', 'content': '', 'tool_calls': [
        {'function': {'name': 'calcular_variacao_percentual',
                      'arguments': {'valor_inicial': 0, 'valor_final': 10}}}
    ]}}
    last = {'message': {'role': 'assistant', 'content': 'Nao posso calcular com base zero.'}}
    with patch('atlas_agent.pedir_ollama', side_effect=[first, last]) as model:
        text, tools = atlas.executar_pedido('Calcule de 0 para 10', rapido=True)
    assert 'Nao posso' in text
    assert tools[0]['resultado'].get('erro')
    assert model.call_count == 2


def test_api_chat_rapido_true_por_padrao():
    client = TestClient(app)
    sid = client.post('/api/session').json()['session_id']
    with patch('backend.api.executar_pedido', return_value=('60%', [])) as model:
        response = client.post('/api/chat', json={'session_id': sid, 'pergunta': '250 a 400'})
    assert response.status_code == 200
    assert response.json()['modo_rapido'] is True
    assert response.json()['duracao_segundos'] >= 0
    assert model.call_args.kwargs['rapido'] is True


def test_api_chat_permite_modo_detalhado():
    client = TestClient(app)
    sid = client.post('/api/session').json()['session_id']
    with patch('backend.api.executar_pedido', return_value=('Detalhado', [])) as model:
        response = client.post('/api/chat', json={'session_id': sid, 'pergunta': 'Descreva', 'rapido': False})
    assert response.status_code == 200
    assert response.json()['modo_rapido'] is False
    assert model.call_args.kwargs['rapido'] is False
