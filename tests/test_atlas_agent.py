import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
import atlas_agent as a

SAMPLE = [{'data':'01/01/2026','valor':'1.00'}, {'data':'01/02/2026','valor':'2.00'}, {'data':'01/03/2026','valor':'-0.50'}]


def test_variacao_original():
    assert a.calcular_variacao_percentual(120, 150)['variacao_percentual'] == '25.00'


def test_variacao_zero():
    with pytest.raises(ValueError): a.calcular_variacao_percentual(0, 10)


def test_variacao_nan_e_bool():
    with pytest.raises(ValueError): a.calcular_variacao_percentual('NaN', 1)
    with pytest.raises(ValueError): a.calcular_variacao_percentual(True, 1)


def test_parse_ordena_e_decimal():
    rows = a.parse_ipca(list(reversed(SAMPLE)))
    assert rows[0]['data'] == '2026-01-01'
    assert rows[-1]['valor_percentual'] == '-0.50'


def test_parse_rejeita_duplicada():
    with pytest.raises(ValueError): a.parse_ipca(SAMPLE + [SAMPLE[0]])


def test_parse_rejeita_vazio():
    with pytest.raises(ValueError): a.parse_ipca([])


def test_acumulado_composto_nao_e_soma():
    rows = a.parse_ipca(SAMPLE[:2])
    result = a.analisar_serie(rows)
    assert result['acumulado_composto_periodo_percentual'] == '3.02'
    assert result['media_mensal_percentual'] == '1.50'


def test_consulta_mockada():
    r = Mock(); r.json.return_value = SAMPLE; r.raise_for_status.return_value = None
    ctx = a.Context()
    with patch('atlas_agent.requests.get', return_value=r) as get:
        out = a.consultar_ipca(ctx, 3)
    assert out['quantidade'] == 3
    assert get.call_args.kwargs['timeout'] == (5, 20)
    assert 'ultimos/3' in get.call_args.args[0]


def test_consulta_rejeita_meses_invalidos():
    with pytest.raises(ValueError): a.consultar_ipca(a.Context(), 121)
    with pytest.raises(ValueError): a.consultar_ipca(a.Context(), True)


def test_consulta_erro_rede():
    ctx = a.Context()
    with patch('atlas_agent.requests.get', side_effect=a.requests.Timeout('timeout')):
        with pytest.raises(a.AtlasError, match='Nao foi possivel'):
            a.consultar_ipca(ctx, 12)
    assert ctx.ipca_rows is None


def test_relatorio_usa_somente_dados_consultados(tmp_path, monkeypatch):
    monkeypatch.setattr(a, 'OUTPUT_DIR', tmp_path)
    ctx = a.Context(ipca_rows=a.parse_ipca(SAMPLE), ipca_url='https://api.bcb.gov.br/example')
    result = a.gerar_relatorio_ipca(ctx, 'Relatorio teste')
    content = Path(result['arquivo']).read_text(encoding='utf-8')
    assert '3.02' not in content or '2026-03-01' in content
    assert 'Acumulado composto' in content
    assert 'https://api.bcb.gov.br/example' in content
    assert 'nao demonstram as causas' in content


def test_relatorio_sem_consulta_bloqueado():
    with pytest.raises(ValueError): a.gerar_relatorio_ipca(a.Context(), 'Teste')


def test_dispatch_rejeita_funcao_desconhecida():
    with pytest.raises(a.AtlasError): a.dispatch('executar_shell', {}, a.Context())


def test_dispatch_rejeita_parametro_extra():
    with pytest.raises(a.AtlasError): a.dispatch('analisar_ipca', {'caminho': 'C:/'}, a.Context())


def test_encadeamento_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(a, 'LOG_DIR', tmp_path)
    first = {'message': {'role': 'assistant', 'content':'', 'tool_calls': [
        {'function': {'name':'calcular_variacao_percentual', 'arguments': {'valor_inicial':120, 'valor_final':150}}}]}}
    final = {'message': {'role': 'assistant', 'content':'Aumento de 25%.'}}
    with patch('atlas_agent.pedir_ollama', side_effect=[first, final]) as p:
        text, calls = a.executar_pedido('Qual o aumento?')
    assert '25%' in text
    assert calls[0]['resultado']['variacao_percentual'] == '25.00'
    assert p.call_count == 2
    assert (tmp_path / 'execucoes.jsonl').exists()


def test_fluxo_ipca_sem_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(a, 'LOG_DIR', tmp_path)
    monkeypatch.setattr(a, 'OUTPUT_DIR', tmp_path)
    r = Mock(); r.json.return_value = SAMPLE; r.raise_for_status.return_value = None
    with patch('atlas_agent.requests.get', return_value=r):
        text, calls = a.comando_ipca(3, relatorio=True)
    assert 'IPCA' in text
    assert len(calls) == 3
    assert list(tmp_path.glob('ipca_*.md'))


def test_serie_descontinua_rejeitada():
    rows = a.parse_ipca([SAMPLE[0], SAMPLE[2]])
    with pytest.raises(ValueError, match='descontinua'):
        a.analisar_serie(rows)


def test_cache_mesma_sessao_sem_nova_consulta():
    ctx = a.Context()
    r = Mock(); r.json.return_value = SAMPLE; r.raise_for_status.return_value = None
    with patch('atlas_agent.requests.get', return_value=r) as get:
        first = a.consultar_ipca(ctx, 3)
        second = a.consultar_ipca(ctx, 3)
    assert first['cache'] is False
    assert second['cache'] is True
    assert get.call_count == 1
    assert second['ultima_competencia'] == '2026-03-01'


def test_cache_diferente_intervalo_consulta_novamente():
    ctx = a.Context()
    r3 = Mock(); r3.json.return_value = SAMPLE; r3.raise_for_status.return_value = None
    r4 = Mock(); r4.json.return_value = SAMPLE + [{'data': '01/04/2026', 'valor': '0.25'}]; r4.raise_for_status.return_value = None
    with patch('atlas_agent.requests.get', side_effect=[r3, r4]) as get:
        a.consultar_ipca(ctx, 3)
        a.consultar_ipca(ctx, 4)
    assert get.call_count == 2


def test_cache_expirado_consulta_novamente():
    ctx = a.Context()
    r = Mock(); r.json.return_value = SAMPLE; r.raise_for_status.return_value = None
    with patch('atlas_agent.requests.get', return_value=r) as get:
        a.consultar_ipca(ctx, 3)
        ctx.consultado_em_utc -= a.timedelta(minutes=31)
        a.consultar_ipca(ctx, 3)
    assert get.call_count == 2


def test_contexto_memoria_entre_perguntas(monkeypatch, tmp_path):
    monkeypatch.setattr(a, 'LOG_DIR', tmp_path)
    ctx = a.Context()
    responses = [
        {'message': {'role':'assistant','content':'O IPCA foi consultado.'}},
        {'message': {'role':'assistant','content':'A resposta considera a pergunta anterior.'}},
    ]
    with patch('atlas_agent.pedir_ollama', side_effect=responses) as req:
        a.executar_pedido('Fale sobre IPCA', ctx=ctx)
        a.executar_pedido('E a ultima competencia?', ctx=ctx)
    messages = req.call_args.args[0]
    assert any(msg.get('content') == 'Fale sobre IPCA' for msg in messages)
    assert any(msg.get('content') == 'O IPCA foi consultado.' for msg in messages)


def test_cache_nao_aceita_retorno_descontinuo():
    ctx = a.Context()
    r = Mock(); r.json.return_value = [SAMPLE[0], SAMPLE[2]]; r.raise_for_status.return_value = None
    with patch('atlas_agent.requests.get', return_value=r):
        with pytest.raises(a.AtlasError, match='Nao foi possivel'):
            a.consultar_ipca(ctx, 2)
    assert ctx.ipca_rows is None


def historico_60():
    from datetime import date
    rows = []
    for i in range(60):
        year = 2021 + i // 12
        month = i % 12 + 1
        rows.append({'data': f'{year:04d}-{month:02d}-01',
                     'valor_percentual': str(round(0.2 + month * 0.04 + (i//12)*0.01, 3))})
    return rows


def test_backtest_sem_vazamento_e_12_origens():
    rows = historico_60()
    bt = a.analisar_backtesting(rows)
    assert bt['periodo_teste_inicio'] == '2025-01-01'
    assert bt['periodo_teste_fim'] == '2025-12-01'
    assert len(bt['modelos']) == 3
    assert all(m['amostras'] == 12 for m in bt['modelos'])
    assert bt['melhor_modelo'] == 'sazonal_12m'


def test_forecast_futuro_3_meses():
    out = a.prever_serie(historico_60(), 3)
    assert [r['competencia'] for r in out['previsoes']] == ['2026-01-01', '2026-02-01', '2026-03-01']
    assert out['modelo_escolhido'] in {'ultimo_valor', 'media_12m', 'sazonal_12m'}
    assert out['ultima_competencia_observada'] == '2025-12-01'


def test_forecast_historico_insuficiente():
    with pytest.raises(ValueError, match='36 meses'):
        a.prever_serie(historico_60()[:35], 1)


def test_forecast_horizonte_invalido():
    with pytest.raises(ValueError, match='horizonte'):
        a.prever_serie(historico_60(), 7)
    with pytest.raises(ValueError, match='horizonte'):
        a.prever_serie(historico_60(), True)


def test_forecast_serie_descontinua():
    rows = historico_60()
    del rows[14]
    with pytest.raises(ValueError, match='descontinua'):
        a.prever_serie(rows, 3)


def test_forecast_no_contexto_e_dispatch():
    ctx = a.Context(ipca_rows=historico_60())
    result = a.dispatch('prever_ipca', {'horizonte': 2}, ctx)
    assert result['horizonte_meses'] == 2
    with pytest.raises(a.AtlasError):
        a.dispatch('prever_ipca', {'horizonte': 2, 'shell': 'x'}, ctx)


def test_gera_relatorio_previsao(tmp_path, monkeypatch):
    monkeypatch.setattr(a, 'OUTPUT_DIR', tmp_path)
    ctx = a.Context(ipca_rows=historico_60(), ipca_url='https://api.bcb.gov.br/mock')
    result = a.gerar_relatorio_previsao(ctx, 2)
    content = Path(result['arquivo']).read_text(encoding='utf-8')
    assert 'MAE' in content and 'RMSE' in content
    assert '2026-02-01' in content
    assert 'nao oficiais' in content.lower()


def test_comando_previsao_integrado_sem_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(a, 'OUTPUT_DIR', tmp_path)
    monkeypatch.setattr(a, 'LOG_DIR', tmp_path)
    ctx = a.Context()
    rows = historico_60()
    def fake_consultar(ctx, meses):
        ctx.ipca_rows = rows
        ctx.ipca_url = 'https://api.bcb.gov.br/mock'
        return {'quantidade': 60, 'cache': False, 'ultima_competencia': rows[-1]['data'],
                'url_consulta': ctx.ipca_url}
    monkeypatch.setattr(a, 'consultar_ipca', fake_consultar)
    message, calls = a.comando_previsao(60, 3, relatorio=True, ctx=ctx)
    assert 'MAE' in message
    assert len(calls) == 3
    assert list(tmp_path.glob('previsao_ipca_*.md'))


def test_url_historico_60_usa_intervalo_em_vez_de_ultimos():
    from datetime import date
    url = a.url_consulta_ipca(60, date(2026, 11, 10))
    assert '/ultimos/' not in url
    assert 'dataInicial=01/05/2021' in url
    assert 'dataFinal=10/11/2026' in url


def test_ultimos_20_mantem_endpoint_simples():
    assert '/ultimos/20?formato=json' in a.url_consulta_ipca(20)


def test_consulta_60_seleciona_60_mais_recentes():
    from datetime import date
    valores = []
    for i in range(66):
        ano = 2021 + i // 12
        mes = i % 12 + 1
        valores.append({'data': f'01/{mes:02d}/{ano:04d}', 'valor': '0.35'})
    response = Mock()
    response.json.return_value = valores
    response.raise_for_status.return_value = None
    with patch('atlas_agent.requests.get', return_value=response) as get:
        result = a.consultar_ipca(a.Context(), 60)
    assert result['quantidade'] == 60
    assert result['registros'][0]['data'] == '2021-07-01'
    assert result['registros'][-1]['data'] == '2026-06-01'
    assert 'dataInicial=' in get.call_args.args[0]


def test_consulta_60_rejeita_resposta_curta():
    response = Mock()
    response.json.return_value = SAMPLE
    response.raise_for_status.return_value = None
    with patch('atlas_agent.requests.get', return_value=response):
        with pytest.raises(a.AtlasError, match='apenas 3 observacoes'):
            a.consultar_ipca(a.Context(), 60)
