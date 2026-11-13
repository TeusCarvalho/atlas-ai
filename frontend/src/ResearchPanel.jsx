import React, {useEffect, useState} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {BookOpen, FileText, LoaderCircle, Search, UploadCloud, Trash2, RefreshCw, ShieldCheck, AlertTriangle} from 'lucide-react'
import {apiFetch, apiGet, apiPost} from './apiClient.js'

export default function ResearchPanel(){
  const [docs,setDocs] = useState([])
  const [selected,setSelected] = useState('')
  const [file,setFile] = useState(null)
  const [question,setQuestion] = useState('')
  const [answer,setAnswer] = useState(null)
  const [busy,setBusy] = useState(false)
  const [loading,setLoading] = useState(true)
  const [error,setError] = useState('')
  const [info,setInfo] = useState('')

  const load=async()=>{
    const result=await apiGet('/research/documents')
    setDocs(result.documents || [])
  }
  useEffect(()=>{let active=true
    apiGet('/research/documents').then(data=>{if(active)setDocs(data.documents||[])})
      .catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setLoading(false)})
    return()=>{active=false}
  },[])

  const upload=async e=>{
    e.preventDefault()
    const formElement=e.currentTarget
    if(!file)return
    setBusy(true);setError('');setInfo('')
    try{
      const form=new FormData();form.append('file',file)
      const response=await apiFetch('/research/upload',{method:'POST',body:form})
      const data=await response.json().catch(()=>({}))
      if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:`HTTP ${response.status}`)
      await load()
      setSelected(data.document.id)
      setFile(null)
      formElement.reset()
      setInfo(`Documento indexado: ${data.document.chunks} trechos. Texto armazenado no Supabase.`)
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  const ask=async e=>{
    e.preventDefault();if(!question.trim())return
    setBusy(true);setError('');setAnswer(null);setInfo('')
    try{
      const result=await apiPost('/research/ask',{pergunta:question.trim(),document_id:selected||null})
      setAnswer(result)
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  const remove=async d=>{
    if(!window.confirm(`Excluir os trechos e embeddings de "${d.filename}" do Supabase?`))return
    setBusy(true);setError('')
    try{
      await apiPost('/research/delete',{document_id:d.id})
      if(selected===d.id)setSelected('')
      setAnswer(null);await load();setInfo('Documento excluído.')
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  return <div className="research-root">
    <section className="panel">
      <div className="panel-title"><div><h2><BookOpen size={19}/> Biblioteca de documentos</h2>
      <p>RAG com Ollama local e Supabase pgvector. PDF com texto, TXT e Markdown.</p></div>
      <button className="outline" onClick={()=>{setLoading(true);load().catch(e=>setError(e.message)).finally(()=>setLoading(false))}}><RefreshCw size={15}/> Atualizar</button></div>
      <div className="notice research-privacy"><ShieldCheck size={17}/> Ao enviar, o texto extraído e seus vetores serão guardados no Supabase da sua conta. O arquivo original não será mantido. Evite documentos sigilosos.</div>
      <form className="research-upload" onSubmit={upload}>
        <label htmlFor="rag-file">Arquivo de até 2 MB (PDF, TXT ou MD; PDF até 60 páginas)</label>
        <input id="rag-file" type="file" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" onChange={e=>setFile(e.target.files?.[0]||null)} required/>
        <button className="primary" disabled={busy||!file} type="submit">{busy?<LoaderCircle size={16} className="spin"/>:<UploadCloud size={16}/>} Indexar documento</button>
      </form>
      {loading?<p>Carregando biblioteca…</p>:docs.length?<div className="research-docs">
        {docs.map(d=><div className="research-doc" key={d.id}>
          <FileText size={18}/><div><b>{d.filename}</b><small>{d.pages} pág. · {d.chunk_count} trechos · {new Date(d.created_at).toLocaleDateString('pt-BR')}</small></div>
          <button type="button" disabled={busy} className="outline" onClick={()=>remove(d)} aria-label={`Excluir ${d.filename}`}><Trash2 size={15}/></button>
        </div>)}
      </div>:<div className="empty">Nenhum documento indexado. Comece pelo arquivo de exemplo.</div>}
    </section>
    <section className="panel">
      <div className="panel-title"><div><h2><Search size={19}/> Perguntar aos documentos</h2>
      <p>O Atlas recupera os trechos mais próximos da pergunta e apresenta suas fontes.</p></div></div>
      <form className="research-query" onSubmit={ask}>
        <label>Escopo da pesquisa
          <select value={selected} onChange={e=>{setSelected(e.target.value);setAnswer(null)}}>
            <option value="">Todos os meus documentos</option>
            {docs.map(d=><option value={d.id} key={d.id}>{d.filename}</option>)}
          </select>
        </label>
        <label>Pergunta
          <textarea rows="3" maxLength={1000} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ex.: Qual é o procedimento de conferência descrito no documento?" required/>
        </label>
        <button className="primary" type="submit" disabled={busy||!question.trim()||docs.length===0}>{busy?<LoaderCircle className="spin" size={16}/>:<Search size={16}/>} Consultar documentos</button>
      </form>
      {error&&<div className="alert" role="alert"><AlertTriangle size={16}/>{error}</div>}
      {info&&<div className="notice" role="status">{info}</div>}
      {answer&&<div className="research-answer"><h3>Resposta do Atlas</h3>
        <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{answer.resposta}</ReactMarkdown></div>
        <h3>Trechos recuperados ({answer.fontes.length})</h3>
        {answer.fontes.length===0?<p>Sem fontes relevantes para esta pergunta.</p>:<div className="research-sources">{answer.fontes.map((s,i)=><details key={`${s.document_id}-${s.page_number}-${i}`}>
          <summary>Fonte {i+1} · {s.filename} · página {s.page_number} · similaridade {Number(s.similarity).toFixed(2)}</summary>
          <p>{s.content}</p>
        </details>)}</div>}
        <p className="research-hint">Respostas de IA podem conter erros. Verifique os trechos antes de utilizá-las em decisões importantes.</p>
      </div>}
    </section>
  </div>
}
