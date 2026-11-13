from unittest.mock import patch
from fastapi.testclient import TestClient
import backend.api as api
from atlas_pipeline import ResultadoPipeline

client = TestClient(api.app)


def sample():
    from atlas_agent import analisar_serie, prever_serie
    from atlas_pipeline import backtesting_horizontes, validar_saida
    rows = [{'data':f'{2021+i//12:04d}-{i%12+1:02d}-01','valor_percentual':str(.2+(i%12)*.03)} for i in range(60)]
    forecast=prever_serie(rows,3)
    bt=backtesting_horizontes(rows)
    result=ResultadoPipeline(analisar_serie(rows), forecast, bt, validar_saida(rows,forecast,bt),
        [{'agente':'Coletor','acao':'consultar_ipca','status':'ok','detalhe':'simulado'}],
        'https://api.bcb.gov.br/mock','2026-11-10T00:00:00Z',False)
    return result,rows


def new_session():
    response=client.post('/api/session')
    assert response.status_code==200
    return response.json()['session_id']


def test_health():
    assert client.get('/api/health').json()['scope']=='local'


def test_analyze_rejects_invalid_inputs():
    sid=new_session()
    assert client.post('/api/analyze',json={'session_id':sid,'meses':12,'horizonte':3}).status_code==422
    assert client.post('/api/analyze',json={'session_id':sid,'meses':60,'horizonte':7}).status_code==422


def test_unknown_session_fails_closed():
    assert client.post('/api/report',json={'session_id':'a'*32}).status_code==404


def test_report_requires_analysis():
    sid=new_session()
    assert client.post('/api/report',json={'session_id':sid}).status_code==409


def test_analysis_and_report_mocked():
    sid=new_session()
    result,rows=sample()
    def fake_run(ctx,meses,horizonte):
        ctx.ipca_rows=rows
        return result
    with patch('backend.api.executar_pipeline',side_effect=fake_run):
        response=client.post('/api/analyze',json={'session_id':sid,'meses':60,'horizonte':3})
    assert response.status_code==200, response.text
    assert len(response.json()['painel']['metricas'])==9
    report=client.post('/api/report',json={'session_id':sid})
    assert report.status_code==200
    assert 'Backtesting por horizonte' in report.json()['markdown']


def test_chat_with_fake_ollama():
    sid=new_session()
    with patch('backend.api.executar_pedido',return_value=('25%',[{'ferramenta':'calcular_variacao_percentual'}])):
        response=client.post('/api/chat',json={'session_id':sid,'pergunta':'Calcule 120 para 150'})
    assert response.status_code==200
    assert response.json()['resposta']=='25%'


def test_clear_invalidates_stored_report():
    sid=new_session()
    s=api.session_for(sid)[1]
    s.last_result=sample()[0]
    assert client.post('/api/session/clear',json={'session_id':sid}).status_code==200
    assert client.post('/api/report',json={'session_id':sid}).status_code==409
