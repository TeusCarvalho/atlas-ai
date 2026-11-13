"""Geracao do relatorio consolidado (metodologia e backtesting multi-horizonte)."""
from __future__ import annotations
from atlas_pipeline import ResultadoPipeline


def texto_relatorio(resultado: ResultadoPipeline) -> str:
    if not resultado.verificacao['aprovado']:
        raise ValueError('Verificacao bloqueou o relatorio.')
    pred = resultado.previsao
    bt = resultado.avaliacao
    linhas = [
        '# Atlas Agent Studio — Relatorio IPCA experimental', '',
        f'Consulta UTC: {resultado.consulta_utc}',
        f'Fonte primaria: {resultado.fonte}',
        f'Ultima competencia observada: {pred["ultima_competencia_observada"]}',
        f'Historico de {pred["meses_historicos"]} meses; horizonte: {pred["horizonte_meses"]} meses.',
        '', '## Indicadores',
        f'- IPCA ultimo mes: {resultado.resumo["ultimo_mes_percentual"]}%',
        f'- Acumulado composto do periodo: {resultado.resumo["acumulado_composto_periodo_percentual"]}%',
        '', '## Previsoes experimentais',
        f'Modelo escolhido pelo MAE de um passo: {pred["modelo_escolhido"]}.',
        '', '| Competencia | IPCA mensal previsto (%) |', '|---|---:|',
    ]
    linhas.extend(f'| {x["competencia"]} | {x["ipca_mensal_previsto_percentual"]:.4f} |'
                  for x in pred['previsoes'])
    linhas.extend(['', '## Backtesting por horizonte',
                   f'Origem rolling; numero de alvos por horizonte: {bt["origens"]}.',
                   'Erros em pontos percentuais (p.p.).',
                   '', '| Horizonte | Modelo | MAE (p.p.) | RMSE (p.p.) | Amostras |',
                   '|---:|---|---:|---:|---:|'])
    linhas.extend(f'| {x["horizonte"]} | {x["modelo"]} | {x["mae_pp"]:.4f} | {x["rmse_pp"]:.4f} | {x["amostras"]} |'
                  for x in bt['metricas'])
    linhas.extend(['', '## Verificacao',
                   f'Validação quantitativa: {"aprovada" if resultado.verificacao["aprovado"] else "reprovada"}.',
                   '', '## Limitacoes'])
    linhas.extend('- ' + text for text in resultado.verificacao['ressalvas'])
    linhas.extend(['- Selecao do modelo da v4.1 pelo backtesting de um passo; '
                   'avaliacao por horizonte e diagnostica, nao altera a selecao.',
                   '- Nenhuma estimativa representa previsao oficial.',
                   '- Esta serie nao permite inferir causalidade economica.', ''])
    return '\n'.join(linhas)
