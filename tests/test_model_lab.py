"""Testes de regressão Model Lab sem depender de Ollama ou conexão externa."""
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import model_lab
from backend.api import app

client = TestClient(app)


def fake_models():
    return {'models': [
        {'name': 'qwen3:4b-instruct', 'size': 3_200_000_000},
        {'name': 'outro:latest', 'size': 2_000_000_000},
        {'name': 'nomic-embed-text:latest', 'size': 100},
        {'name': 13, 'size': 7},
    ]}


def response_for(body):
    user = body['messages'][-1]['content']
    if 'tools' in body:
        message = {'role':'assistant', 'content':'', 'tool_calls': [
            {'function': {'name': 'calcular_variacao_percentual', 'arguments': {'valor_inicial':120, 'valor_final':150}}}
        ]}
    elif 'ATLAS' in user:
        message = {'role':'assistant', 'content': 'ATLAS'}
    elif 'preço do diesel' in user:
        message = {'role':'assistant', 'content': 'O preço não consta na fonte.'}
    else:
        message = {'role':'assistant', 'content': 'É necessária assinatura digital do encarregado. [Fonte 1]'}
    return {
        'message': message, 'done_reason':'stop',
        'total_duration': 1_300_000_000, 'load_duration': 200_000_000,
        'eval_count': 50, 'eval_duration': 1_000_000_000,
        'prompt_eval_count': 80,
    }


def mocked_request(method, path, *, payload=None, timeout=12):
    if path == '/api/tags':
        return fake_models()
    if path == '/api/ps':
        return {'models': [{'name': 'qwen3:4b-instruct', 'size_vram': 3_100_000_000}]}
    if path == '/api/chat':
        return response_for(payload)
    raise AssertionError('path inesperado')


def test_list_models_filters_embedding_and_malformed():
    with patch.object(model_lab, '_json_request', side_effect=mocked_request):
        rows = model_lab.list_models()
    assert [r['name'] for r in rows] == ['outro:latest', 'qwen3:4b-instruct']
    assert rows[1]['size_gb'] == 3.2


def test_running_models_shows_vram_reported_only():
    with patch.object(model_lab, '_json_request', side_effect=mocked_request):
        rows = model_lab.running_models()
    assert rows[0]['size_vram_gb'] == 3.1


def test_instrucao_requires_exact_output():
    assert model_lab.check_response('instrucao', {'content': 'ATLAS'})[0]
    assert not model_lab.check_response('instrucao', {'content':'ATLAS\nExplicação'})[0]


def test_tool_call_validates_arguments():
    okay = {'tool_calls':[{'function':{'name':'calcular_variacao_percentual','arguments':'{"valor_inicial":120,"valor_final":150}'}}]}
    bad = {'tool_calls':[{'function':{'name':'calcular_variacao_percentual','arguments':{'valor_inicial':120,'valor_final':100}}}]}
    assert model_lab.check_response('ferramenta', okay)[0]
    assert not model_lab.check_response('ferramenta', bad)[0]


def test_tool_call_never_executes_function():
    assert not model_lab.check_response('ferramenta', {'content':'Aumento de 25%', 'tool_calls':[]})[0]


def test_context_requires_citation():
    yes={'content':'Assinatura digital do encarregado. [Fonte 1]'}
    no={'content':'Assinatura digital do encarregado.'}
    assert model_lab.check_response('contexto', yes)[0]
    assert not model_lab.check_response('contexto', no)[0]


def test_abstention_rejects_invented_price():
    assert model_lab.check_response('abstencao', {'content':'Não há informação de preço na fonte.'})[0]
    assert not model_lab.check_response('abstencao', {'content':'Não há informação, mas custa R$ 8,00.'})[0]


def test_benchmark_single_model_has_four_scenarios():
    with patch.object(model_lab, '_json_request', side_effect=mocked_request):
        r = model_lab.run_benchmark(['qwen3:4b-instruct'])
    assert r['summary'][0]['checks_passed'] == 4
    assert r['summary'][0]['score_percent'] == 100.0
    assert r['summary'][0]['average_tps'] == 50
    assert len(r['results']) == 4
    assert {row['scenario'] for row in r['results']} == {'instrucao','ferramenta','contexto','abstencao'}
    assert all(row['load_duration_s'] == 0.2 for row in r['results'])


def test_comparison_sequential_and_repetitions():
    bodies=[]
    def recording(method,path,*,payload=None,timeout=12):
        if path == '/api/chat': bodies.append(payload)
        return mocked_request(method,path,payload=payload,timeout=timeout)
    with patch.object(model_lab, '_json_request', side_effect=recording):
        r = model_lab.run_benchmark(['qwen3:4b-instruct','outro:latest'],2)
    assert len(r['results']) == 16
    assert [x['model'] for x in r['summary']] == ['qwen3:4b-instruct','outro:latest']
    assert all(b['think'] is False and b['stream'] is False for b in bodies)
    assert len(bodies) == 16
    assert [b['model'] for b in bodies[:8]] == ['qwen3:4b-instruct'] * 8


@pytest.mark.parametrize('names,repetitions', [([],1), (['qwen3:4b-instruct']*2,1), (['qwen3:4b-instruct'],3), (['nomic-embed-text:latest'],1), (['fake'],1), (['a','b','c'],1)])
def test_benchmark_rejects_invalid_inputs(names,repetitions):
    with patch.object(model_lab,'_json_request',side_effect=mocked_request):
        with pytest.raises(ValueError):
            model_lab.run_benchmark(names,repetitions)


def test_failure_is_reported_without_fake_score():
    def fail_some(method,path,*,payload=None,timeout=12):
        if path == '/api/chat' and payload['tools'] if payload and 'tools' in payload else False:
            raise model_lab.ModelLabError('Modelo sem suporte de tools.')
        return mocked_request(method,path,payload=payload,timeout=timeout)
    with patch.object(model_lab, '_json_request', side_effect=fail_some):
        r=model_lab.run_benchmark(['qwen3:4b-instruct'])
    assert r['summary'][0]['score_percent'] == 75.0
    assert r['summary'][0]['errors'] == 1
    assert any(x['error'] for x in r['results'])


def test_restricted_ollama_endpoints():
    with pytest.raises(ValueError):
        model_lab._json_request('GET','/not-allowed')


def test_lab_routes_in_local_mode():
    with patch.object(model_lab, '_json_request', side_effect=mocked_request):
        available=client.get('/api/lab/models')
        assert available.status_code == 200
        assert available.json()['models'][0]['name']=='outro:latest'
        run=client.post('/api/lab/benchmark',json={'models':['qwen3:4b-instruct']})
    assert run.status_code == 200
    assert len(run.json()['results']) == 4


def test_lab_validation_at_http_boundary():
    assert client.post('/api/lab/benchmark',json={'models':[], 'repetitions':1}).status_code == 422
    assert client.post('/api/lab/benchmark',json={'models':['a'], 'repetitions':5}).status_code == 422


def test_lab_offline_returns_503():
    with patch.object(model_lab,'list_models',side_effect=model_lab.ModelLabError('Ollama indisponível')):
        result = client.get('/api/lab/models')
    assert result.status_code == 503
    assert 'indisponível' in result.json()['detail']


def test_api_client_never_accepts_external_url():
    with pytest.raises(ValueError):
        model_lab._json_request('POST','https://example.org/api/chat',payload={})
