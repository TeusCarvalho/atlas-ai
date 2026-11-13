import React, {useEffect, useState} from 'react'
import { Activity, AlertTriangle, BarChart3, Bot, CheckCircle2, CircleHelp, Cpu, FlaskConical, Gauge, LoaderCircle, RefreshCw, XCircle } from 'lucide-react'
import {apiGet, apiPost} from './apiClient.js'

const decimal = (n, places = 2) => n == null ? '—' : Number(n).toLocaleString('pt-BR', {maximumFractionDigits:places, minimumFractionDigits:places})
const scenarios = [
  ['instrucao', 'Formato e instruções'],
  ['ferramenta', 'Tool calling'],
  ['contexto', 'Contexto com fonte'],
  ['abstencao', 'Resposta sem evidência'],
]

export default function ModelLabPanel() {
  const [models, setModels] = useState([])
  const [running, setRunning] = useState([])
  const [selected, setSelected] = useState([])
  const [repetitions, setRepetitions] = useState(1)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  async function refresh() {
    setLoading(true)
    setError('')
    try {
      const data = await apiGet('/lab/models')
      const entries = data.models || []
      setModels(entries)
      setRunning(data.running || [])
      setSelected(prev => {
        const valid = prev.filter(name => entries.some(x => x.name === name))
        return valid.length ? valid : entries.find(x => x.name === 'qwen3:4b-instruct') ? ['qwen3:4b-instruct'] : (entries[0] ? [entries[0].name] : [])
      })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [])

  function toggleModel(name) {
    setSelected(current => current.includes(name) ? current.filter(n => n !== name) : current.length < 2 ? [...current, name] : current)
  }

  async function run(e) {
    e.preventDefault()
    if (!selected.length || busy) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const output = await apiPost('/lab/benchmark', {models: selected, repetitions})
      setResult(output)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return <div className="model-lab-root">
    <section className="panel">
      <div className="panel-title">
        <div><h2><FlaskConical size={19}/> Laboratório de modelos locais</h2><p>Compare velocidade, comportamento e uso de ferramentas com testes controlados.</p></div>
        <button type="button" className="outline" onClick={refresh} disabled={busy || loading}><RefreshCw size={15}/> Atualizar</button>
      </div>
      <div className="notice lab-notice"><CircleHelp size={18}/> Os testes utilizam o Ollama no seu computador. Nenhum modelo será baixado automaticamente e os resultados não são enviados ao Supabase.</div>
      {loading && <div className="lab-working"><LoaderCircle size={17} className="spin"/> Consultando modelos instalados…</div>}
      {error && <div role="alert" className="alert"><AlertTriangle size={17}/>{error}</div>}
      {!loading && models.length === 0 && <div className="empty">Nenhum modelo de chat detectado. Confira se o Ollama está aberto e se qwen3:4b-instruct está instalado.</div>}
      {models.length > 0 && <form onSubmit={run} className="lab-form">
        <fieldset disabled={busy} className="lab-fieldset">
          <legend>Escolha até dois modelos</legend>
          <div className="lab-model-list">
            {models.map(model => <label key={model.name} className={`lab-model-item ${selected.includes(model.name) ? 'selected' : ''}`}>
              <input type="checkbox" checked={selected.includes(model.name)} disabled={!selected.includes(model.name) && selected.length >= 2} onChange={() => toggleModel(model.name)}/>
              <span><strong>{model.name}</strong><small>{decimal(model.size_gb)} GB em disco (estimado)</small></span>
              <Bot size={19}/>
            </label>)}
          </div>
        </fieldset>
        <div className="lab-actions">
          <label>Repetições por cenário
            <select value={repetitions} onChange={e => setRepetitions(Number(e.target.value))} disabled={busy}>
              <option value={1}>1 — teste rápido</option><option value={2}>2 — maior amostragem</option>
            </select>
          </label>
          <button className="primary" disabled={busy || !selected.length} type="submit">
            {busy ? <LoaderCircle className="spin" size={17}/> : <Gauge size={17}/>}
            {busy ? 'Executando…' : 'Executar benchmark'}
          </button>
        </div>
        <p className="lab-explain">Serão realizadas {selected.length * repetitions * 4} chamadas ao modelo, em sequência. A execução pode demorar, principalmente ao comparar modelos maiores. Mantenha o Ollama e o FastAPI abertos.</p>
      </form>}
    </section>

    {running.length > 0 && <section className="panel lab-ps"><h2><Cpu size={19}/> Modelos carregados na memória</h2>
      <div className="lab-chips">{running.map(model => <span className="lab-chip" key={model.name}>{model.name} · VRAM carregada: {model.size_vram_gb == null ? 'não informada' : `${decimal(model.size_vram_gb)} GB`}</span>)}</div>
      <p>Memória de modelo reportada por <code>/api/ps</code>, não consumo total da GPU.</p>
    </section>}

    <section className="panel">
      <h2><BarChart3 size={19}/> O que medimos?</h2>
      <div className="lab-cases">{scenarios.map(([key, label]) => <div key={key} className="lab-case"><span className="lab-case-icon"><Activity size={18}/></span><div><b>{label}</b><p>{key === 'instrucao' ? 'Segue um formato exato de resposta.' : key === 'ferramenta' ? 'Seleciona a ferramenta e fornece os argumentos corretos. Não executa operações.' : key === 'contexto' ? 'Usa uma fonte fictícia fornecida e cita a referência. Não exercita busca pgvector.' : 'Admite quando a fonte não informa um dado solicitado.'}</p></div></div>)}</div>
    </section>

    {result && <>
      <section className="panel"><h2>Resultados dos modelos</h2>
        <div className="lab-summary-grid">{result.summary.map(s => <div className="lab-summary-card" key={s.model}>
          <b>{s.model}</b>
          <strong>{decimal(s.score_percent, 1)}%</strong>
          <small>{s.checks_passed}/{s.checks_total} verificações específicas aprovadas</small>
          <dl><div><dt>Tempo médio (requisição)</dt><dd>{decimal(s.average_duration_s)} s</dd></div><div><dt>Velocidade de geração média</dt><dd>{decimal(s.average_tps)} tok/s</dd></div><div><dt>Falhas técnicas</dt><dd>{s.errors}</dd></div></dl>
        </div>)}</div>
        <p className="lab-disclaimer">A pontuação de aprovação NÃO é uma medida geral de inteligência, acurácia ou qualidade de RAG. Modelos e equipamentos diferentes podem alterar os tempos.</p>
      </section>
      <section className="panel"><h2>Detalhes por cenário</h2>
        <div className="table-scroll"><table className="lab-table"><thead><tr><th>Modelo</th><th>Cenário</th><th>Resultado</th><th>Tempo</th><th>Geração</th><th>Tokens</th><th>Detalhes</th></tr></thead>
          <tbody>{result.results.map((r, i) => <tr key={`${r.model}-${r.scenario}-${r.repetition}-${i}`}>
            <td><b>{r.model}</b><small>Repetição {r.repetition}</small></td><td>{r.scenario_name}</td>
            <td><span className={`lab-result ${r.passed ? 'ok' : 'fail'}`}>{r.passed ? <CheckCircle2 size={14}/> : <XCircle size={14}/>} {r.passed ? 'Passou' : 'Não passou'}</span></td>
            <td>{decimal(r.duration_s)} s</td><td>{decimal(r.tokens_per_second)} tok/s</td><td>{r.output_tokens}</td>
            <td><details><summary>Inspecionar</summary><div className="lab-inspect"><p>{r.error || r.criterion}</p><p>Tempo interno Ollama: {decimal(r.ollama_duration_s)} s · carregamento: {decimal(r.load_duration_s)} s</p><p>Tokens de entrada: {r.prompt_tokens ?? '—'} · motivo da parada: {r.done_reason || '—'}</p>{r.tool_calls?.length > 0 && <p>Ferramentas solicitadas: {r.tool_calls.join(', ')}</p>}{r.response_preview && <pre>{r.response_preview}</pre>}</div></details></td>
          </tr>)}</tbody></table></div>
      </section>
      <section className="panel"><h2>Interpretação dos resultados</h2><div className="lab-footnotes">{result.notes.map((note,i)=><p key={i}>• {note}</p>)}</div></section>
    </>}
  </div>
}
