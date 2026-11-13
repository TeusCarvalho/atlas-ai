"""Orquestracao verificavel: especialistas Python, modelo Ollama opcional na aba Chat.

Nao e um sistema de agentes autonomos independentes: cada papel e um estagio
especializado e deterministico com resultados rastreaveis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import sqrt, isfinite
from typing import Any
import atlas_agent as core

MODELS = ('ultimo_valor', 'media_12m', 'sazonal_12m')


def backtesting_horizontes(rows: list[dict[str, str]], horizontes: tuple[int, ...] = (1, 2, 3), origens: int = 12) -> dict[str, Any]:
    """Rolling-origin sem vazamento; h>1 inclui previsoes recursivas intermediarias.

    Usa as ultimas `origens` competencias como alvos finais para cada horizonte.
    Todos os modelos usam o mesmo conjunto de alvos para cada horizonte.
    """
    core.validar_continuidade(rows)
    if len(rows) < 36:
        raise ValueError('Sao necessarios pelo menos 36 meses de dados.')
    if not isinstance(origens, int) or isinstance(origens, bool) or not 6 <= origens <= 24:
        raise ValueError('origens deve estar entre 6 e 24.')
    if not horizontes or any(type(h) is not int or not 1 <= h <= 6 for h in horizontes):
        raise ValueError('horizontes devem estar entre 1 e 6 meses.')
    if len(set(horizontes)) != len(horizontes):
        raise ValueError('Nao repita horizontes.')
    values = [float(core.decimal_num(row['valor_percentual'])) for row in rows]
    tests = []
    for h in sorted(horizontes):
        if len(values) - origens - h + 1 < 24:
            raise ValueError('Historico insuficiente para os horizontes e origens solicitados.')
        for model in MODELS:
            outcomes = []
            for target_index in range(len(values) - origens, len(values)):
                cutoff = target_index - h + 1
                history = values[:cutoff]
                pred = None
                for _ in range(h):
                    pred = core.prever_um_passo(history, model)
                    history.append(pred)
                assert pred is not None
                outcomes.append({'competencia': rows[target_index]['data'],
                                 'real': round(values[target_index], 5),
                                 'previsto': round(pred, 5),
                                 'erro_pp': round(values[target_index] - pred, 5)})
            errs = [x['erro_pp'] for x in outcomes]
            mae = sum(abs(e) for e in errs) / len(errs)
            rmse = sqrt(sum(e * e for e in errs) / len(errs))
            tests.append({'horizonte': h, 'modelo': model, 'mae_pp': round(mae, 4),
                          'rmse_pp': round(rmse, 4), 'amostras': len(errs),
                          'resultados': outcomes})
    best = {}
    for h in sorted(horizontes):
        best[h] = min((x for x in tests if x['horizonte'] == h),
                      key=lambda row: (row['mae_pp'], row['rmse_pp'], row['modelo']))['modelo']
    return {'metricas': tests, 'melhores_por_horizonte': best,
            'origens': origens, 'periodo_teste': [rows[-origens]['data'], rows[-1]['data']],
            'nota': 'Backtesting rolling-origin por horizonte, com 12 alvos finais por padrao; '
                    'erros expressos em pontos percentuais. O passado nao garante acerto futuro.'}


def validar_saida(rows: list[dict[str, str]], previsao: dict[str, Any],
                  avaliacao: dict[str, Any]) -> dict[str, Any]:
    """Auditoria quantitativa basica, sem aval de qualidade preditiva de producao."""
    issues: list[str] = []
    core.validar_continuidade(rows)
    if previsao.get('ultima_competencia_observada') != rows[-1]['data']:
        issues.append('Ultima competencia da previsao diverge dos dados observados.')
    horizon = previsao.get('horizonte_meses')
    predictions = previsao.get('previsoes', [])
    if horizon != len(predictions):
        issues.append('Quantidade de previsoes diverge do horizonte.')
    expected = rows[-1]['data']
    for prediction in predictions:
        expected = core.proximo_mes(expected)
        if prediction.get('competencia') != expected:
            issues.append('Competencias previstas nao sao consecutivas.')
        value = prediction.get('ipca_mensal_previsto_percentual')
        if type(value) not in (float, int) or not isfinite(value):
            issues.append('Valor previsto invalido.')
    if not avaliacao.get('metricas'):
        issues.append('Metricas de backtesting ausentes.')
    return {'aprovado': not issues, 'alertas': issues,
            'ressalvas': [
                'Estimativas experimentais, sem intervalo de confianca calibrado.',
                'O menor erro historico nao garante maior precisao futura.',
                'Serie agregada do IPCA nao explica causas da inflacao.',
            ]}


@dataclass
class ResultadoPipeline:
    resumo: dict[str, Any]
    previsao: dict[str, Any]
    avaliacao: dict[str, Any]
    verificacao: dict[str, Any]
    etapas: list[dict[str, Any]] = field(default_factory=list)
    fonte: str = ''
    consulta_utc: str = ''
    cache: bool = False


def executar_pipeline(ctx: core.Context, meses: int = 60, horizonte: int = 3) -> ResultadoPipeline:
    """Coletor -> Analista -> Previsor -> Verificador, sem LLM nos calculos."""
    if type(meses) is not int or not 36 <= meses <= 120:
        raise ValueError('Historico deve estar entre 36 e 120 meses.')
    if type(horizonte) is not int or not 1 <= horizonte <= 6:
        raise ValueError('Horizonte deve estar entre 1 e 6 meses.')
    steps: list[dict[str, Any]] = []
    consulted = core.consultar_ipca(ctx, meses)
    steps.append({'agente': 'Coletor', 'acao': 'consultar_ipca', 'status': 'ok',
                  'detalhe': f'{len(ctx.ipca_rows or [])} meses, cache: {consulted["cache"]}'})
    summary = core.analisar_ipca(ctx)
    steps.append({'agente': 'Analista', 'acao': 'analisar_ipca', 'status': 'ok',
                  'detalhe': f'Acumulado: {summary["acumulado_composto_periodo_percentual"]}%'})
    prediction = core.prever_ipca(ctx, horizonte)
    # Reduz origens apenas quando o historico curto exige treino inicial >= 24 meses.
    origens = min(12, meses - 24 - horizonte + 1)
    evaluated = backtesting_horizontes(ctx.ipca_rows or [], tuple(range(1, horizonte + 1)), origens=origens)
    steps.append({'agente': 'Previsor', 'acao': 'prever_e_avaliar', 'status': 'ok',
                  'detalhe': f'Modelo: {prediction["modelo_escolhido"]}'})
    checked = validar_saida(ctx.ipca_rows or [], prediction, evaluated)
    steps.append({'agente': 'Verificador', 'acao': 'validar_resultados',
                  'status': 'ok' if checked['aprovado'] else 'alerta',
                  'detalhe': 'Dados e horizontes conferidos' if checked['aprovado'] else '; '.join(checked['alertas'])})
    return ResultadoPipeline(summary, prediction, evaluated, checked, steps,
                             consulted['url_consulta'], consulted['consultado_em_utc'], consulted['cache'])
