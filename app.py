"""Atlas Agent Studio v5 — interface web local.

Iniciar com: python -m streamlit run app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from atlas_agent import AtlasError, Context, executar_pedido, MODEL
from atlas_pipeline import executar_pipeline
from dashboard_data import preparar_painel
from relatorio_v5 import texto_relatorio

st.set_page_config(page_title='Atlas Agent Studio', page_icon='🧭', layout='wide', initial_sidebar_state='expanded')

st.markdown('''<style>
.block-container{padding-top:1.8rem;max-width:1400px}
[data-testid="stMetric"]{background:rgba(128,128,128,.07);border-radius:12px;padding:15px}
h1,h2,h3{letter-spacing:-.025em}
</style>''', unsafe_allow_html=True)

if 'atlas_ctx' not in st.session_state:
    st.session_state.atlas_ctx = Context()
if 'atlas_painel' not in st.session_state:
    st.session_state.atlas_painel = None
if 'atlas_chat' not in st.session_state:
    st.session_state.atlas_chat = []

with st.sidebar:
    st.title('🧭 Atlas Agent')
    st.caption('Studio v5 · execução local · dados oficiais')
    meses = st.slider('Histórico (meses)', min_value=36, max_value=120, value=60, step=12)
    horizonte = st.slider('Horizonte da previsão (meses)', min_value=1, max_value=6, value=3)
    st.caption('Modelo local: ' + MODEL)
    if st.button('🧹 Limpar sessão', use_container_width=True):
        st.session_state.atlas_ctx = Context()
        st.session_state.atlas_painel = None
        st.session_state.atlas_chat = []
        st.success('Sessão e cache limpos.')
    st.divider()
    st.caption('A API do Banco Central exige internet. O chat requer Ollama iniciado no computador.')
    st.caption('Não há autenticação nesta versão: use somente localmente.')

st.title('Atlas Agent Studio')
st.caption('Dados históricos, previsões experimentais, métricas e execução de ferramentas em um painel.')

tab_dashboard, tab_models, tab_audit, tab_chat = st.tabs(['📈 Economia', '🧪 Modelos', '🔎 Auditoria', '💬 Assistente'])

with tab_dashboard:
    left, right = st.columns([1, 3], vertical_alignment='bottom')
    with left:
        analyze = st.button('▶ Consultar e analisar', type='primary', use_container_width=True)
    with right:
        st.caption('Fluxo: Coletor → Analista → Previsor → Verificador. Os cálculos são Python, não texto gerado pela IA.')
    if analyze:
        try:
            with st.spinner('Consultando série oficial e executando backtesting...'):
                result = executar_pipeline(st.session_state.atlas_ctx, meses, horizonte)
                st.session_state.atlas_painel = preparar_painel(result, st.session_state.atlas_ctx.ipca_rows or [])
            st.success('Consulta, previsão e verificação concluídas.')
        except (AtlasError, ValueError, OSError) as exc:
            st.error(f'Falha na análise: {exc}')
    view = st.session_state.atlas_painel
    if view:
        metrics = view['indicadores']
        c1,c2,c3,c4 = st.columns(4)
        c1.metric('Último IPCA mensal', f"{metrics['ultimo_ipca']:.2f}%")
        c2.metric('Acumulado do período', f"{metrics['acumulado']:.2f}%")
        c3.metric('Última competência', metrics['ultima_competencia'][:7])
        c4.metric('Meses observados', metrics['amostra'])
        st.subheader('IPCA mensal: observado e estimado')
        original = pd.DataFrame(view['serie']).rename(columns={'ipca_observado': 'Observado (%)'})
        estimate = pd.DataFrame(view['previsoes']).rename(columns={'ipca_previsto': 'Previsto (%)'})
        display = original.merge(estimate, on='competencia', how='outer').sort_values('competencia')
        display['competencia'] = pd.to_datetime(display['competencia'])
        st.line_chart(display.set_index('competencia')[['Observado (%)','Previsto (%)']], height=360)
        st.caption('Valores após a última observação são previsões experimentais e não dados oficiais.')
        col1,col2=st.columns([1,1])
        with col1:
            st.subheader('Previsões mensais')
            st.dataframe(estimate.rename(columns={'competencia':'Competência'}), use_container_width=True, hide_index=True)
        with col2:
            st.subheader('Histórico recente')
            st.dataframe(original.tail(12).iloc[::-1], use_container_width=True, hide_index=True)
        st.caption(f"Fonte: {view['fonte']} | Consulta UTC: {view['consulta_utc']} | Cache: {'sim' if view['cache'] else 'não'}")
        st.link_button('Fonte oficial — Banco Central', view['fonte'])
        with st.expander('Limitações e metodologia'):
            for caution in view['ressalvas']:
                st.write('• ' + caution)
            st.write('Seleção do modelo atual: menor MAE no backtesting de um passo da versão 4.1. '
                     'A tabela de modelos apresenta adicionalmente erros por horizonte.')
    else:
        st.info('Clique em “Consultar e analisar” para carregar a série oficial e visualizar os gráficos.')

with tab_models:
    view = st.session_state.atlas_painel
    if not view:
        st.info('Execute a consulta na aba Economia primeiro.')
    else:
        st.subheader('Backtesting por horizonte')
        st.caption('Métricas calculadas separadamente para cada horizonte com origens temporais sucessivas; MAE e RMSE em pontos percentuais.')
        data = pd.DataFrame(view['metricas'])
        st.dataframe(data, hide_index=True, use_container_width=True)
        st.subheader('MAE por modelo e horizonte')
        st.bar_chart(data.pivot(index='horizonte',columns='modelo',values='mae_pp'))
        st.caption('O melhor modelo escolhido para a previsão ainda é determinado pelo teste de um mês da v4.1.')

with tab_audit:
    view = st.session_state.atlas_painel
    if not view:
        st.info('Execute a consulta na aba Economia primeiro.')
    else:
        st.subheader('Etapas especializadas')
        for step in view['rastreabilidade']:
            st.write(f"**{step['agente']}** · {step['acao']} · {step['status']} — {step['detalhe']}")
        st.divider()
        st.caption('Identificador da sessão: ' + st.session_state.atlas_ctx.run_id)
        st.caption('A sessão é mantida apenas no processo local. Logs JSONL podem conter perguntas. Não os publique.')
        if st.button('📝 Gerar relatório Markdown'):
            try:
                result = executar_pipeline(st.session_state.atlas_ctx, len(view['serie']), len(view['previsoes']))
                content = texto_relatorio(result).encode('utf-8')
                st.session_state['last_report'] = {
                    'name': f'atlas_relatorio_{st.session_state.atlas_ctx.run_id}.md',
                    'bytes': content}
                st.success('Relatório completo gerado, incluindo métricas multi-horizonte.')
            except (ValueError, OSError) as exc:
                st.error(f'Falha ao gerar relatório: {exc}')
        if 'last_report' in st.session_state:
            file = st.session_state['last_report']
            st.download_button('⬇ Baixar relatório', data=file['bytes'], file_name=file['name'], mime='text/markdown')

with tab_chat:
    st.subheader('Assistente local com Ollama')
    st.caption('Perguntas em linguagem natural. O modelo pode escolher as ferramentas Python autorizadas; as respostas devem ser conferidas.')
    for message in st.session_state.atlas_chat:
        with st.chat_message(message['role']):
            st.write(message['content'])
            if message.get('tools'):
                with st.expander('Ferramentas utilizadas'):
                    st.json(message['tools'])
    question = st.chat_input('Ex.: calcule a variação de 120 para 150')
    if question:
        st.session_state.atlas_chat.append({'role': 'user', 'content': question})
        with st.chat_message('user'):
            st.write(question)
        with st.chat_message('assistant'):
            try:
                with st.spinner('Consultando Ollama local...'):
                    reply, calls = executar_pedido(question, ctx=st.session_state.atlas_ctx)
                st.write(reply)
                if calls:
                    with st.expander('Ferramentas utilizadas'):
                        st.json(calls)
                st.session_state.atlas_chat.append({'role':'assistant','content':reply,'tools':calls})
            except (AtlasError, ValueError, OSError) as exc:
                st.error('Falha no Ollama ou ferramenta: ' + str(exc))
