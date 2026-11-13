import React, {useEffect, useRef, useState} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {FileSpreadsheet, Upload, LoaderCircle, AlertCircle, BarChart3} from 'lucide-react'
import {apiFetch} from './apiClient.js'

const n=(v,d=2)=>Number(v).toLocaleString('pt-BR',{maximumFractionDigits:d})

export default function DataPanel({session, chatHistory, setChatHistory, onPersist}) {
  const dataChatFeedRef=useRef(null)
  const [result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  const [question,setQuestion]=useState(''),[asking,setAsking]=useState(false),[askError,setAskError]=useState('')
  useEffect(()=>{
    if(!session)return
    let active=true
    apiFetch('/data/summary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:session})})
      .then(r=>r.ok?r.json():null).then(json=>{if(active && json?.resumo)setResult(json.resumo)}).catch(()=>{})
    return()=>{active=false}
  },[session])
  useEffect(()=>{
    if(!result)return
    const feed=dataChatFeedRef.current
    if(feed)feed.scrollTo({top:feed.scrollHeight,behavior:asking?'smooth':'auto'})
  },[chatHistory,asking,result])
  async function askData(e){
    e.preventDefault(); const text=question.trim()
    if(!text||!result||!session||asking)return
    setQuestion('');setAskError('');setAsking(true)
    setChatHistory(prev=>[...prev,{role:'user',text}])
    try{
      const response=await apiFetch('/data/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:session,pergunta:text})})
      const data=await response.json().catch(()=>({}))
      if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:`HTTP ${response.status}`)
      setChatHistory(prev=>[...prev,{role:'assistant',text:data.resposta,tools:data.ferramentas}]); onPersist?.()
    }catch(err){setAskError(err.message)}finally{setAsking(false)}
  }
  async function handleUpload(e){
    const file=e.target.files?.[0]; if(!file || !session) return
    setError('');setBusy(true);setResult(null);setAskError('');setChatHistory([])
    try {
      if(file.size>8*1024*1024) throw Error('Arquivo acima do limite de 8 MB.')
      const form=new FormData(); form.append('session_id',session);form.append('file',file)
      const response=await apiFetch('/data/upload',{method:'POST',body:form})
      const json=await response.json().catch(()=>({}))
      if(!response.ok) throw Error(typeof json.detail==='string'?json.detail:`HTTP ${response.status}`)
      setResult(json.resumo); onPersist?.()
    }catch(err){setError(err.message)}finally{setBusy(false);e.target.value=''}
  }
  const chart=result?.distribuicao
  const cat=result?.categoricas?.find(item=>item.valores?.length)
  return <>
    <section className="panel data-upload">
      <div className="panel-title"><div><h2>Atlas Data Analyst</h2><p>Diagnóstico automático de CSV e Excel, com cálculos realizados pelo Python.</p></div><FileSpreadsheet size={26} className="soft"/></div>
      <label className="dropzone"><Upload size={22}/><strong>{busy?'Analisando arquivo…':'Escolher arquivo CSV ou XLSX'}</strong><small>Até 8 MB · 50 mil linhas · 80 colunas · primeira aba do Excel</small><input type="file" accept=".csv,.xlsx" disabled={!session||busy} onChange={handleUpload} aria-label="Selecionar planilha" /></label>
      <div className="notice">Arquivo processado na API local, sem envio do conteúdo completo ao Ollama e sem salvar o arquivo original. O DataFrame e o resumo permanecem temporariamente na memória do backend; apenas o esquema das colunas e suas perguntas são enviados ao Ollama local. Somente metadados agregados e mensagens são persistidos no Supabase quando configurado. Não envie dados sensíveis sem revisar o projeto de segurança.</div>
    </section>
    {error&&<div className="alert" role="alert"><AlertCircle size={18}/>{error}</div>}
    {result&&<>
      <section className="panel data-chat"><div className="panel-title"><div><h2>Pergunte sobre sua planilha</h2><p>O Qwen3 escolhe uma ferramenta autorizada; o Python calcula. Sem executar código do modelo.</p></div></div>
        <div className="data-suggestions">{['Qual a soma de receita por regiao?','Qual produto tem maior receita total?','Quantas linhas existem na planilha?'].map(q=><button type="button" key={q} className="outline" onClick={()=>setQuestion(q)}>{q}</button>)}</div>
        <div className="data-chat-feed" ref={dataChatFeedRef} role="log" aria-label="Mensagens sobre a planilha">{chatHistory.length===0?<div className="empty">Envie uma pergunta sobre soma, média, contagem, mínimo, máximo, valores distintos ou nulos. Você também pode agrupar por coluna e filtrar por igualdade.</div>:
          chatHistory.map((item,i)=><div className={`bubble ${item.role}`} key={i}><span>{item.role==='user'?'Você':'Atlas Data'}</span><div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{item.text}</ReactMarkdown></div>{item.tools?.length>0&&<details><summary>Ferramenta executada</summary><pre>{JSON.stringify(item.tools,null,2)}</pre></details>}</div>)}
        {asking&&<div className="chat-pending" role="status"><LoaderCircle className="spin" size={15}/> Atlas Data está respondendo…</div>}</div>
        {askError&&<div role="alert" className="alert">{askError}</div>}
        <form className="chat-form" onSubmit={askData}><input aria-label="Pergunta sobre planilha" maxLength={1000} value={question} onChange={e=>setQuestion(e.target.value)} disabled={asking} placeholder="Ex.: Qual a receita total por região?"/><button className="primary" disabled={asking||!question.trim()}>{asking?'Consultando…':'Perguntar'}</button></form>
      </section>
      <div className="metrics"><div className="metric"><span>Linhas</span><strong>{n(result.linhas,0)}</strong><small>{result.arquivo}</small></div><div className="metric"><span>Colunas</span><strong>{n(result.colunas_total,0)}</strong><small>Campos identificados</small></div><div className="metric"><span>Células vazias</span><strong>{n(result.celulas_ausentes,0)}</strong><small>Valores ausentes</small></div><div className="metric"><span>Linhas duplicadas</span><strong>{n(result.linhas_duplicadas,0)}</strong><small>Duplicatas exatas</small></div></div>
      {chart&&<section className="panel"><div className="panel-title"><div><h2>Distribuição: {chart.coluna}</h2><p>Frequência por faixa de valores</p></div><BarChart3 className="soft"/></div><div className="data-bars">{chart.faixas.map((d,i)=><div className="data-bar-row" key={i}><span title={d.faixa}>{d.faixa}</span><div className="data-bar-track"><div style={{width:`${d.quantidade/Math.max(1,...chart.faixas.map(x=>x.quantidade))*100}%`}}/></div><b>{n(d.quantidade,0)}</b></div>)}</div></section>}
      {result.numericas.length>0&&<section className="panel"><h2>Indicadores numéricos</h2><div className="table-scroll"><table><thead><tr><th>Coluna</th><th>Média</th><th>Mediana</th><th>Min.</th><th>Máx.</th><th>Soma</th></tr></thead><tbody>{result.numericas.map(c=><tr key={c.coluna}><td>{c.coluna}</td><td>{n(c.media,4)}</td><td>{n(c.mediana,4)}</td><td>{n(c.minimo,4)}</td><td>{n(c.maximo,4)}</td><td>{n(c.soma,4)}</td></tr>)}</tbody></table></div></section>}
      {cat&&<section className="panel"><h2>Valores mais frequentes: {cat.coluna}</h2><div className="data-bars">{cat.valores.map((d,i)=><div className="data-bar-row" key={i}><span title={d.categoria}>{d.categoria}</span><div className="data-bar-track"><div style={{width:`${d.quantidade/Math.max(1,...cat.valores.map(x=>x.quantidade))*100}%`}}/></div><b>{n(d.quantidade,0)}</b></div>)}</div></section>}
      <section className="panel"><h2>Qualidade das colunas</h2><div className="table-scroll"><table><thead><tr><th>Coluna</th><th>Tipo</th><th>Ausentes</th><th>% ausentes</th><th>Distintos</th></tr></thead><tbody>{result.colunas.map(c=><tr key={c.nome}><td>{c.nome}</td><td>{c.tipo}</td><td>{n(c.ausentes,0)}</td><td>{n(c.ausentes_percentual)}%</td><td>{n(c.unicos,0)}</td></tr>)}</tbody></table></div></section>
      <section className="panel"><h2>Amostra (primeiras 8 linhas)</h2><div className="table-scroll"><table><thead><tr>{result.colunas.map(c=><th key={c.nome}>{c.nome}</th>)}</tr></thead><tbody>{result.amostra.map((row,i)=><tr key={i}>{result.colunas.map(c=><td key={c.nome}>{row[c.nome]===null?'—':String(row[c.nome])}</td>)}</tr>)}</tbody></table></div></section>
    </>}
  </>
}
