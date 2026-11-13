import React, {useEffect, useMemo, useRef, useState} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import DataPanel from './DataPanel.jsx'
import ResearchPanel from './ResearchPanel.jsx'
import ModelLabPanel from './ModelLabPanel.jsx'
import { Activity, ArrowUpRight, Bot, ChartColumnIncreasing, CheckCircle2, CircleAlert, Database, Download, FileSpreadsheet, FlaskConical, History, BookOpen, LogOut, LoaderCircle, Menu, MessageCircle, RefreshCw, ShieldCheck, Workflow, Gauge, X } from 'lucide-react'
import AuthGate from './AuthGate.jsx'
import {supabase, authConfigError} from './supabase.js'
import {apiPost, apiGet} from './apiClient.js'

const route = apiPost
const format = (x, digits = 2) => Number(x).toLocaleString('pt-BR', {minimumFractionDigits:digits, maximumFractionDigits:digits})
const month = d => { const [y,m] = d.slice(0,7).split('-'); return `${m}/${y}` }
function LineGraph({series, forecasts}) {
  const points = [...series.map(r => ({t:r.competencia,v:r.ipca_observado,forecast:false})), ...forecasts.map(r=>({t:r.competencia,v:r.ipca_previsto,forecast:true}))]
  if(!points.length) return <div className="empty">Consulte os dados para visualizar o gráfico.</div>
  const W=940,H=280,P=38; const min=Math.min(0,...points.map(p=>p.v))-.15,max=Math.max(0,...points.map(p=>p.v))+.15
  const x=i=>P+i*(W-2*P)/Math.max(1,points.length-1),y=v=>H-P-(v-min)*(H-2*P)/(max-min)
  const historical=points.filter(p=>!p.forecast), future=points.slice(Math.max(0,historical.length-1))
  const poly=arr=>arr.map(p=>`${x(points.indexOf(p))},${y(p.v)}`).join(' ')
  return <div className="chart-scroll"><svg role="img" aria-label="Gráfico do IPCA mensal observado e previsto" viewBox={`0 0 ${W} ${H}`} className="line-chart">
    {[0,.25,.5,.75,1].map(i=>{const val=min+i*(max-min);return <g key={i}><line x1={P} y1={y(val)} x2={W-P} y2={y(val)} stroke="#243147"/><text x={P-8} y={y(val)+4} textAnchor="end" fill="#8796ad" fontSize="12">{format(val,1)}</text></g>})}
    <line x1={P} y1={y(0)} x2={W-P} y2={y(0)} stroke="#64748b" strokeDasharray="4 5"/>
    <polyline fill="none" stroke="#4f9cff" strokeWidth="3" strokeLinejoin="round" points={poly(historical)}/>
    <polyline fill="none" stroke="#44d3ad" strokeDasharray="7 5" strokeWidth="3" strokeLinejoin="round" points={poly(future)}/>
    {forecasts.map(p=>{const i=points.findIndex(v=>v.t===p.competencia);return <circle key={p.competencia} cx={x(i)} cy={y(p.ipca_previsto)} r="5" fill="#44d3ad"><title>{month(p.competencia)}: {format(p.ipca_previsto)}% previsto</title></circle>})}
    {points.filter((_,i)=>i%12===0 || i===points.length-1).map(p=><text key={p.t} x={x(points.indexOf(p))} y={H-7} textAnchor="middle" fill="#8796ad" fontSize="12">{month(p.t)}</text>)}
  </svg></div>
}
function Card({label,value,detail}){return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>}
const tools=[{key:'economia',label:'Economia',Icon:ChartColumnIncreasing},{key:'modelos',label:'Modelos',Icon:FlaskConical},{key:'auditoria',label:'Auditoria',Icon:Workflow},{key:'assistente',label:'Assistente',Icon:MessageCircle},{key:'dados',label:'Atlas Data',Icon:FileSpreadsheet},{key:'historico',label:'Histórico',Icon:History},{key:'research',label:'Deep Research',Icon:BookOpen},{key:'lab',label:'Model Lab',Icon:Gauge}]
function Studio({authSession}){
  const [tab,setTab]=useState('economia'), [sess,setSess]=useState(null),[health,setHealth]=useState(null)
  const [menuOpen,setMenuOpen]=useState(false)
  const chatFeedRef=useRef(null)
  const [meses,setMeses]=useState(60),[horizonte,setHorizonte]=useState(3),[panel,setPanel]=useState(null)
  const [busy,setBusy]=useState(false),[chatBusy,setChatBusy]=useState(false),[error,setError]=useState(''),[chatError,setChatError]=useState('')
  const [fastMode,setFastMode]=useState(true)
  const [messages,setMessages]=useState([]),[prompt,setPrompt]=useState(''),[dataReset,setDataReset]=useState(0),[dataChat,setDataChat]=useState([])
  const [savedRuns,setSavedRuns]=useState([]),[archive,setArchive]=useState(false)
  useEffect(()=>{
    let active=true
    Promise.all([fetch('/api/health').then(r=>r.json()).then(h=>{if(h.status!=='ok')throw Error('API indisponível'); return h}), route('/session'), apiGet('/history'), apiGet('/messages')])
      .then(([h,s,r,m])=>{if(active){
        if(Boolean(h.authenticated)!==Boolean(supabase)) throw Error('Configuração Supabase diferente entre frontend e backend.')
        setHealth(h);setSess(s.session_id);setSavedRuns(r.runs || [])
        setMessages((m.messages||[]).filter(x=>x.channel==='assistente').map(x=>({role:x.role,text:x.body,tools:x.tools})))
        setDataChat((m.messages||[]).filter(x=>x.channel==='dados').map(x=>({role:x.role,text:x.body,tools:x.tools})))
      }})
      .catch(e=>{if(active)setError(`Inicialização: ${e.message}`)})
    return()=>{active=false}
  },[])
  // Mantem a ultima mensagem visivel ao enviar, receber e reabrir o chat.
  useEffect(()=>{
    if(tab!=='assistente')return
    const feed=chatFeedRef.current
    if(!feed)return
    feed.scrollTo({top:feed.scrollHeight,behavior:chatBusy?'smooth':'auto'})
  },[messages,chatBusy,tab])
  // A gaveta mobile pode ser fechada por Esc; nao bloquear a rolagem da pagina.
  useEffect(()=>{
    if(!menuOpen)return
    const close=(event)=>{if(event.key==='Escape')setMenuOpen(false)}
    window.addEventListener('keydown',close)
    return()=>window.removeEventListener('keydown',close)
  },[menuOpen])
  async function reloadHistory(){
    try{const result=await apiGet('/history');setSavedRuns(result.runs||[])}catch(err){setError(err.message)}
  }
  async function openSaved(runId){
    setError('')
    try{
      const result=await route('/history/read',{run_id:runId})
      const run=result.run
      if(run?.category==='economia' && run.payload?.painel){setPanel(run.payload.painel);setArchive(true);setTab('economia')}
      else if(run?.category==='relatorio' && run.payload?.markdown){downloadMarkdown(run.payload.filename||'relatorio.md',run.payload.markdown)}
      else setError('Registro disponível no histórico. Planilhas originais não são armazenadas na nuvem.')
    }catch(err){setError(err.message)}
  }

  async function analyze(){if(!sess)return;setBusy(true);setError('');try{const data=await route('/analyze',{session_id:sess,meses,horizonte});setPanel(data.painel);setArchive(false);await reloadHistory()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function clear(){if(!sess)return;try{await route('/session/clear',{session_id:sess});setPanel(null);setArchive(false);setMessages([]);setDataReset(v=>v+1);setDataChat([]);setError('');setChatError('')}catch(e){setError(e.message)}}
  function downloadMarkdown(filename,markdown){const blob=new Blob([markdown],{type:'text/markdown;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url)}
  async function report(){if(!sess||archive)return;setError('');try{const data=await route('/report',{session_id:sess});downloadMarkdown(data.filename,data.markdown);reloadHistory()}catch(e){setError(e.message)}}
  async function send(e){e.preventDefault();if(!prompt.trim()||!sess||chatBusy)return;const q=prompt.trim();setPrompt('');setMessages(s=>[...s,{role:'user',text:q}]);setChatBusy(true);setChatError('');try{const res=await route('/chat',{session_id:sess,pergunta:q,rapido:fastMode});setMessages(s=>[...s,{role:'assistant',text:res.resposta,tools:res.ferramentas,seconds:res.duracao_segundos}]);reloadHistory()}catch(err){setChatError(err.message)}finally{setChatBusy(false)}}
  const ranked=useMemo(()=>[...(panel?.metricas||[])].sort((a,b)=>a.horizonte-b.horizonte||a.mae_pp-b.mae_pp),[panel])
  return <div className="shell">
    {menuOpen&&<button type="button" className="sidebar-backdrop" aria-label="Fechar menu" onClick={()=>setMenuOpen(false)}/>}
    <aside id="atlas-sidebar" className={`sidebar ${menuOpen?'open':''}`} aria-label="Navegação principal">
    <div className="brand"><div className="brand-icon"><Activity size={22}/></div><div><b>ATLAS</b><small>Agent Studio</small></div></div>
    <div className="eyebrow">WORKSPACE</div>
    <nav>{tools.map(({key,label,Icon})=><button key={key} className={`nav-item ${tab===key?'active':''}`} onClick={()=>{setTab(key);setMenuOpen(false)}}><Icon size={18}/>{label}{tab===key&&<span className="nav-dot"/>}</button>)}</nav>
    <div className="side-bottom"><div className="side-status"><span className="online"/> API {health?'conectada':'não conectada'}</div><small>Modelo: {health?.modelo||'—'}</small><small>{authSession ? `Conta: ${authSession.user?.email || 'autenticada'}` : 'Modo local sem login'}</small><button className="ghost small" onClick={clear} disabled={!sess}><RefreshCw size={14}/> Limpar contexto local</button>{authSession && <button className="ghost small signout-button" onClick={()=>supabase.auth.signOut()}><LogOut size={15}/> Sair da conta</button>}</div>
  </aside>
  <main className="main"><header className="topbar"><div className="topbar-start"><button type="button" className="menu-toggle" aria-label={menuOpen?'Fechar menu de navegação':'Abrir menu de navegação'} aria-expanded={menuOpen} aria-controls="atlas-sidebar" onClick={()=>setMenuOpen(v=>!v)}>{menuOpen?<X size={20}/>:<Menu size={20}/>}</button><span>Studio / <strong>{tools.find(t=>t.key===tab)?.label}</strong></span></div><div className="top-right"><span className="pill"><span className="online"/> Local</span><span className="monospace">v11.0</span></div></header>
    <div className="content"><div className="intro"><div><div className="eyebrow accent">ATLAS AGENT STUDIO</div><h1>{tools.find(t=>t.key===tab)?.label}</h1><p>Dados públicos, modelos explicáveis e agentes locais — tudo em um só lugar.</p></div><div className="intro-icon"><Activity size={30}/></div></div>
    {error&&<div role="alert" className="alert"><CircleAlert size={18}/>{error}</div>}
    {tab==='economia'&&<><section className="control"><div><h2>Consulta e previsão</h2><p>Dados mensais oficiais do IPCA (SGS 433)</p></div><div className="ctrl-group"><label>Histórico <select value={meses} onChange={e=>setMeses(Number(e.target.value))}>{[36,48,60,72,84,96,108,120].map(x=><option key={x} value={x}>{x} meses</option>)}</select></label><label>Horizonte <select value={horizonte} onChange={e=>setHorizonte(Number(e.target.value))}>{[1,2,3,4,5,6].map(x=><option key={x} value={x}>{x} meses</option>)}</select></label><button className="primary" onClick={analyze} disabled={busy||!sess}>{busy?<LoaderCircle className="spin" size={17}/>:<ArrowUpRight size={17}/>} {busy?'Analisando…':'Executar análise'}</button></div></section>
    {panel?<>{archive&&<div className="notice">Visualizando resultado salvo no histórico. Execute uma nova análise para gerar outro relatório.</div>}<div className="metrics"><Card label="Último IPCA" value={`${format(panel.indicadores.ultimo_ipca)}%`} detail={month(panel.indicadores.ultima_competencia)}/><Card label="Acumulado do período" value={`${format(panel.indicadores.acumulado)}%`} detail="Variação composta"/><Card label="Histórico" value={`${panel.indicadores.amostra} meses`} detail="Observações"/><Card label="Modelo" value={panel.indicadores.modelo.replaceAll('_',' ')} detail="Seleção por MAE de 1 passo"/></div>
    <section className="panel"><div className="panel-title"><div><h2>Evolução do IPCA</h2><p>Variação mensal observada e projeções experimentais</p></div><div className="legend"><span><i className="blue"/> Observado</span><span><i className="green"/> Estimado</span></div></div><LineGraph series={panel.serie} forecasts={panel.previsoes}/></section>
    <div className="columns"><section className="panel"><h2>Próximos meses</h2><p>Estimativas mensais (não oficiais)</p><table><thead><tr><th>Competência</th><th>IPCA previsto</th></tr></thead><tbody>{panel.previsoes.map(row=><tr key={row.competencia}><td>{month(row.competencia)}</td><td className="strong green-text">{format(row.ipca_previsto,4)}%</td></tr>)}</tbody></table></section><section className="panel"><h2>Contexto dos dados</h2><div className="details"><div><span>Última competência</span><b>{month(panel.indicadores.ultima_competencia)}</b></div><div><span>Cache utilizado</span><b>{panel.cache?'Sim':'Não'}</b></div><div><span>Consulta UTC</span><b>{panel.consulta_utc.slice(0,19).replace('T',' ')}</b></div></div><a href={panel.fonte} target="_blank" rel="noreferrer" className="source">Fonte oficial <ArrowUpRight size={15}/></a></section></div></>:<div className="empty-state"><Database size={28}/><h2>Pronto para analisar</h2><p>Escolha o histórico e o horizonte para consultar o Banco Central e executar os modelos.</p></div>}</>}
    {tab==='modelos'&&<section className="panel"><h2>Backtesting por horizonte</h2><p>Erros em pontos percentuais, avaliados em origens temporais sucessivas.</p>{panel?<><div className="table-scroll"><table><thead><tr><th>Horizonte</th><th>Modelo</th><th>MAE</th><th>RMSE</th><th>Amostras</th></tr></thead><tbody>{ranked.map(row=><tr key={`${row.horizonte}-${row.modelo}`}><td>{row.horizonte} mês(es)</td><td>{row.modelo}</td><td>{format(row.mae_pp,4)}</td><td>{format(row.rmse_pp,4)}</td><td>{row.amostras}</td></tr>)}</tbody></table></div><div className="notice">A seleção de modelo ainda utiliza o backtesting de um passo. Os demais horizontes são avaliações diagnósticas.</div></>:<div className="empty">Execute uma análise na aba Economia.</div>}</section>}
    {tab==='auditoria'&&<section className="panel"><div className="panel-title"><div><h2>Trilha de execução</h2><p>Etapas especializadas e verificação quantitativa</p></div><button onClick={report} className="outline" disabled={!panel||archive}><Download size={16}/> Exportar Markdown</button></div>{panel?<><div className="steps">{panel.rastreabilidade.map((s,i)=><div className="step" key={i}><div className="step-icon">{s.status==='ok'?<CheckCircle2 size={20}/>:<CircleAlert size={20}/>}</div><div><b>{s.agente}</b><span>{s.acao} — {s.detalhe}</span></div><span className="step-status">{s.status}</span></div>)}</div><div className="notice"><ShieldCheck size={18}/> Estimativas experimentais. A aprovação das verificações não garante acerto preditivo.</div></>:<div className="empty">Execute uma análise na aba Economia.</div>}</section>}
    {tab==='research'&&<ResearchPanel/>}
    {tab==='lab'&&<ModelLabPanel/>}
    {tab==='dados'&&<DataPanel key={dataReset} session={sess} chatHistory={dataChat} setChatHistory={setDataChat} onPersist={reloadHistory}/>}
    {tab==='historico'&&<section className="panel"><div className="panel-title"><div><h2>Histórico persistente</h2><p>Resultados associados à sua conta. Planilhas originais não são salvas.</p></div><button className="outline" onClick={reloadHistory}><RefreshCw size={16}/> Atualizar</button></div>
      {!supabase?<div className="notice">Modo local: configure o Supabase para manter resultados ao reiniciar.</div>:savedRuns.length===0?<div className="empty">Nenhum registro salvo. Execute uma análise na aba Economia ou envie uma planilha.</div>:
      <div className="steps">{savedRuns.map(r=><div className="step" key={r.id}><div className="step-icon"><History size={20}/></div><div><b>{r.title}</b><span>{r.summary} · {new Date(r.created_at).toLocaleString('pt-BR')}</span></div>{['economia','relatorio'].includes(r.category)?<button className="outline" onClick={()=>openSaved(r.id)}>{r.category==='relatorio'?'Baixar':'Abrir'}</button>:<span className="step-status">{r.category}</span>}</div>)}</div>}
    </section>}
    {tab==='assistente'&&<section className="panel chat-panel"><div className="panel-title"><div><h2>Assistente Atlas</h2><p>Qwen3 4B Instruct · Ollama local · ferramentas Python autorizadas</p></div><Bot size={25} className="soft"/></div><div className="chat-feed" ref={chatFeedRef} role="log" aria-label="Mensagens do assistente">{messages.length?messages.map((m,i)=><div key={i} className={`bubble ${m.role}`}><span>{m.role==='user'?'Você':'Atlas'}</span><div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{m.text}</ReactMarkdown></div>{m.tools?.length>0&&<details><summary>{m.tools.length} ferramenta(s) utilizada(s)</summary><pre>{JSON.stringify(m.tools,null,2)}</pre></details>}{m.seconds!==undefined&&<small className="response-time">Processamento: {Number(m.seconds).toLocaleString('pt-BR',{maximumFractionDigits:2})} s</small>}</div>):<div className="empty-chat"><Bot size={34}/><h3>Como posso ajudar?</h3><p>Exemplo: calcule a variação percentual de 120 para 150.</p></div>}{chatBusy&&<div className="chat-pending" role="status"><LoaderCircle className="spin" size={15}/> Atlas está respondendo…</div>}</div>{chatError&&<div role="alert" className="alert">{chatError}</div>}<form onSubmit={send} className="chat-form"><input aria-label="Mensagem ao Atlas" value={prompt} maxLength={1000} onChange={e=>setPrompt(e.target.value)} placeholder="Pergunte algo ao Atlas…"/><button className="primary" disabled={!sess||chatBusy||!prompt.trim()}>{chatBusy?'Aguarde…':'Enviar'}</button></form><label className="speed-option"><input type="checkbox" checked={fastMode} disabled={chatBusy} onChange={e=>setFastMode(e.target.checked)} /><span>Modo rápido</span><small>Respostas curtas; cálculos simples usam só uma chamada ao Ollama.</small></label></section>}
    <footer>Atlas Agent Studio v11.0 · Ollama local · Supabase opcional · Previsões não oficiais</footer>
    </div></main></div>
}


export default function App(){
  const [session,setSession]=useState(null)
  const [ready,setReady]=useState(!supabase)
  useEffect(()=>{
    if(!supabase)return
    let active=true
    supabase.auth.getSession().then(({data})=>{if(active){setSession(data.session);setReady(true)}}).catch(()=>{if(active)setReady(true)})
    const {data:{subscription}}=supabase.auth.onAuthStateChange((_event,next)=>{if(active)setSession(next)})
    return()=>{active=false;subscription.unsubscribe()}
  },[])
  if(authConfigError)return <AuthGate errorOnly/>
  if(!ready)return <div className="login-screen"><div className="login-panel">Verificando sessão...</div></div>
  if(supabase&&!session)return <AuthGate/>
  return <Studio key={session?.user?.id||'local'} authSession={session}/>
}
