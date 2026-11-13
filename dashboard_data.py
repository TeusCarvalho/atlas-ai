"""Transformacao de dados da pipeline em tabelas para a interface. Testavel sem Streamlit."""
from __future__ import annotations
from typing import Any
from atlas_pipeline import ResultadoPipeline


def preparar_painel(result: ResultadoPipeline, serie: list[dict[str, str]]) -> dict[str, Any]:
    if not result.verificacao['aprovado']:
        raise ValueError('Resultado bloqueado: verificacao falhou.')
    forecasts = result.previsao['previsoes']
    ranking = result.avaliacao['metricas']
    selected = result.previsao['modelo_escolhido']
    return {
        'indicadores': {
            'ultima_competencia': result.resumo['ultima_competencia'],
            'ultimo_ipca': float(result.resumo['ultimo_mes_percentual']),
            'acumulado': float(result.resumo['acumulado_composto_periodo_percentual']),
            'modelo': selected,
            'amostra': result.previsao['meses_historicos'],
        },
        'serie': [{'competencia': x['data'], 'ipca_observado': float(x['valor_percentual'])} for x in serie],
        'previsoes': [{'competencia': x['competencia'], 'ipca_previsto': x['ipca_mensal_previsto_percentual']} for x in forecasts],
        'metricas': [{'horizonte': row['horizonte'], 'modelo': row['modelo'],
                      'mae_pp': row['mae_pp'], 'rmse_pp': row['rmse_pp'], 'amostras': row['amostras']}
                     for row in ranking],
        'rastreabilidade': result.etapas,
        'fonte': result.fonte,
        'consulta_utc': result.consulta_utc,
        'cache': result.cache,
        'ressalvas': result.verificacao['ressalvas'],
    }
