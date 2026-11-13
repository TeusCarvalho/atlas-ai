from unittest.mock import Mock, patch
import pytest
import atlas_agent as a
import atlas_pipeline as p
from dashboard_data import preparar_painel


def historico_60():
    return [{'data': f'{2021 + i // 12:04d}-{i % 12 + 1:02d}-01',
             'valor_percentual': str(round(.2 + (i % 12 + 1) * .04 + (i//12)*.01, 3))}
            for i in range(60)]


def test_horizontes_independentes():
    rows = historico_60()
    out = p.backtesting_horizontes(rows, (1, 2, 3))
    assert len(out['metricas']) == 9
    assert set(out['melhores_por_horizonte']) == {1, 2, 3}
    assert all(entry['amostras'] == 12 for entry in out['metricas'])


def test_sem_vazamento_temporal_ultimas_observacoes():
    rows = historico_60()
    baseline = p.backtesting_horizontes(rows, (3,))
    altered = [dict(x) for x in rows]
    altered[-1]['valor_percentual'] = '90'
    changed = p.backtesting_horizontes(altered, (3,))
    base_first = next(m for m in baseline['metricas'] if m['modelo'] == 'media_12m')['resultados'][0]
    changed_first = next(m for m in changed['metricas'] if m['modelo'] == 'media_12m')['resultados'][0]
    assert base_first == changed_first
    assert baseline['metricas'] != changed['metricas']


def test_backtest_rejeita_parametros_invalidos():
    rows = historico_60()
    with pytest.raises(ValueError): p.backtesting_horizontes(rows, (7,))
    with pytest.raises(ValueError): p.backtesting_horizontes(rows, (1, 1))
    with pytest.raises(ValueError): p.backtesting_horizontes(rows[:35])


def test_verificador_recusa_datas_erradas():
    rows = historico_60()
    prediction = a.prever_serie(rows, 2)
    forecast = dict(prediction)
    forecast['previsoes'] = [dict(x) for x in prediction['previsoes']]
    forecast['previsoes'][0]['competencia'] = '2020-01-01'
    checked = p.validar_saida(rows, forecast, p.backtesting_horizontes(rows))
    assert checked['aprovado'] is False
    assert any('consecutivas' in issue for issue in checked['alertas'])


def test_pipeline_com_api_simulada(monkeypatch, tmp_path):
    monkeypatch.setattr(a, 'LOG_DIR', tmp_path)
    rows = historico_60()
    api_rows = [{'data': x['data'][8:10] + '/' + x['data'][5:7] + '/' + x['data'][:4],
                 'valor': x['valor_percentual']} for x in rows]
    response = Mock()
    response.json.return_value = api_rows
    response.raise_for_status.return_value = None
    ctx = a.Context()
    with patch('atlas_agent.requests.get', return_value=response) as get:
        result = p.executar_pipeline(ctx, 60, 3)
        again = p.executar_pipeline(ctx, 60, 3)
    assert get.call_count == 1
    assert result.verificacao['aprovado']
    assert [x['agente'] for x in result.etapas] == ['Coletor','Analista','Previsor','Verificador']
    assert again.cache
    view = preparar_painel(result, ctx.ipca_rows)
    assert len(view['serie']) == 60
    assert len(view['previsoes']) == 3
    assert len(view['metricas']) == 9


def test_dashboard_bloqueia_resultados_invalidos():
    rows = historico_60()
    result = p.ResultadoPipeline({}, {}, {}, {'aprovado': False}, [])
    with pytest.raises(ValueError): preparar_painel(result, rows)


def test_previsao_recursiva_horizonte_3():
    vals = historico_60()
    result = p.backtesting_horizontes(vals, (3,))
    seasonal = next(m for m in result['metricas'] if m['modelo'] == 'sazonal_12m')
    assert seasonal['resultados'][-1]['competencia'] == '2025-12-01'
    assert seasonal['amostras'] == 12


def test_36_meses_horizonte_3_aceito_com_menos_origens(monkeypatch):
    rows = historico_60()[:36]
    ctx = a.Context()
    data = [{'data':x['data'][8:10] + '/' + x['data'][5:7] + '/' + x['data'][:4], 'valor':x['valor_percentual']} for x in rows]
    response = Mock()
    response.json.return_value = data
    response.raise_for_status.return_value = None
    with patch('atlas_agent.requests.get', return_value=response):
        result = p.executar_pipeline(ctx, 36, 3)
    assert result.avaliacao['origens'] == 10
    assert result.verificacao['aprovado']


def test_relatorio_v5_metricas_multihorizonte():
    from relatorio_v5 import texto_relatorio
    rows = historico_60()
    forecast = a.prever_serie(rows, 3)
    evaluation = p.backtesting_horizontes(rows)
    summary = a.analisar_serie(rows)
    result = p.ResultadoPipeline(summary, forecast, evaluation,
                                p.validar_saida(rows, forecast, evaluation), [],
                                'https://api.bcb.gov.br/mock', '2026-11-11T00:00:00Z', False)
    content = texto_relatorio(result)
    assert 'Backtesting por horizonte' in content
    assert 'RMSE' in content
    assert 'https://api.bcb.gov.br/mock' in content
    assert '2026-01-01' in content
