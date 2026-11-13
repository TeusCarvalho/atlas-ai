import io
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from dataset_agent import QueryError, ask_dataset, run_query
from backend.api import app


def frame():
    return pd.DataFrame({
        'regiao': ['Norte', 'Sul', 'Norte', 'Sul', None],
        'produto': ['Caneca', 'Poster', 'Caneca', 'Caneca', 'Poster'],
        'receita': [10.0, 20.0, 30.0, 40.0, None],
    })


def params(**kw):
    result = dict(operacao='somar', coluna='receita', agrupar_por='', filtrar_coluna='', filtrar_valor='')
    result.update(kw)
    return result


def test_sum():
    assert run_query(frame(), params())['resultado'] == 100


def test_sum_by_region():
    result = run_query(frame(), params(agrupar_por='regiao'))
    assert result['grupos'][0]['categoria'] in {'Sul', 'Norte'}
    assert next(x for x in result['grupos'] if x['categoria']=='Norte')['valor']==40


def test_filter_eq_case_insensitive():
    result = run_query(frame(),params(filtrar_coluna='regiao',filtrar_valor='norte'))
    assert result['resultado']==40
    assert result['linhas_consideradas']==2


def test_count_all():
    assert run_query(frame(),params(operacao='contar',coluna=''))['resultado']==5


def test_null_and_unique():
    assert run_query(frame(),params(operacao='nulos'))['resultado']==1
    assert run_query(frame(),params(operacao='unicos',coluna='produto'))['resultado']==2


def test_unknown_column_rejected():
    with pytest.raises(QueryError,match='Coluna nao encontrada'):
        run_query(frame(),params(coluna='outro'))


def test_injection_like_operation_rejected():
    with pytest.raises(QueryError,match='Operacao nao autorizada'):
        run_query(frame(),params(operacao='__import__'))
    with pytest.raises(QueryError,match='contrato autorizado'):
        run_query(frame(),dict(params(),codigo='print(1)'))


def test_non_numeric_rejected():
    with pytest.raises(QueryError,match='nao e numerica'):
        run_query(frame(),params(coluna='regiao'))


def test_nonexistent_filter_yields_controlled_error():
    with pytest.raises(QueryError,match='Nenhum registro'):
        run_query(frame(),params(filtrar_coluna='produto',filtrar_valor='Inexistente'))


def test_llm_tool_call_then_python_result():
    fake={'message':{'tool_calls':[{'function':{'name':'consultar_planilha','arguments':params(agrupar_por='regiao')}}]}}
    with patch('dataset_agent.pedir_ollama',return_value=fake):
        answer,tools=ask_dataset(frame(),'Qual a receita por região?')
    assert 'Norte' in answer
    assert tools[0]['resultado']['total_grupos']==3


def test_llm_refusal_to_call_tool_is_not_hallucination():
    with patch('dataset_agent.pedir_ollama',return_value={'message':{'content':'Inventei a soma: R$ 1000'}}):
        with pytest.raises(QueryError,match='Nao foi possivel identificar'):
            ask_dataset(frame(),'Qual a soma?')


def test_malicious_tool_call_fails_closed():
    fake={'message':{'tool_calls':[{'function':{'name':'executar_python','arguments':{}}}]}}
    with patch('dataset_agent.pedir_ollama',return_value=fake):
        with pytest.raises(QueryError,match='nao autorizada'):
            ask_dataset(frame(),'Execute python')


def test_backend_requires_upload_and_cleans_dataset():
    with TestClient(app) as client:
        sid=client.post('/api/session').json()['session_id']
        assert client.post('/api/data/ask',json={'session_id':sid,'pergunta':'Conte'}).status_code==409
        raw=b'produto,receita\nCaneca,10\nPoster,20\n'
        uploaded=client.post('/api/data/upload',data={'session_id':sid},files={'file':('vendas.csv',io.BytesIO(raw),'text/csv')})
        assert uploaded.status_code==200,uploaded.text
        fake={'message':{'tool_calls':[{'function':{'name':'consultar_planilha','arguments':params(operacao='somar')}}]}}
        with patch('dataset_agent.pedir_ollama',return_value=fake):
            response=client.post('/api/data/ask',json={'session_id':sid,'pergunta':'Soma receita?'})
        assert response.status_code==200,response.text
        assert response.json()['ferramentas'][0]['resultado']['resultado']==30
        client.post('/api/session/clear',json={'session_id':sid})
        assert client.post('/api/data/ask',json={'session_id':sid,'pergunta':'Soma receita?'}).status_code==409


def test_two_sessions_isolated():
    with TestClient(app) as client:
        a=client.post('/api/session').json()['session_id']
        b=client.post('/api/session').json()['session_id']
        raw=b'produto,receita\nCaneca,10\n'
        client.post('/api/data/upload',data={'session_id':a},files={'file':('vendas.csv',io.BytesIO(raw),'text/csv')})
        assert client.post('/api/data/ask',json={'session_id':b,'pergunta':'soma?'}).status_code==409
