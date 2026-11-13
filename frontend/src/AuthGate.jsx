import React, {useState} from 'react'
import {Activity, LockKeyhole, LogIn, Mail, ShieldCheck} from 'lucide-react'
import {supabase, authConfigError} from './supabase.js'

export default function AuthGate({errorOnly = false}) {
  const [email, setEmail] = useState(''), [password, setPassword] = useState('')
  const [register, setRegister] = useState(false), [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(''), [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault()
    setError(''); setMessage(''); setBusy(true)
    try {
      const result = register
        ? await supabase.auth.signUp({email: email.trim(), password})
        : await supabase.auth.signInWithPassword({email: email.trim(), password})
      if(result.error) throw result.error
      if(register && !result.data.session) setMessage('Cadastro recebido. Confirme seu e-mail antes de entrar.')
    } catch (err) {setError(err.message)} finally {setBusy(false)}
  }
  return <div className="login-screen"><div className="login-panel">
    <div className="login-brand"><div className="brand-icon"><Activity size={24}/></div><div><b>ATLAS</b><small>Agent Studio · v9</small></div></div>
    <div className="login-mark"><ShieldCheck size={27}/></div><h1>Seu workspace de IA</h1>
    <p>Entre para consultar seus relatórios, análises e conversas salvas no Supabase.</p>
    {authConfigError || errorOnly ? <div className="alert">Configuração incompleta: informe VITE_SUPABASE_URL e VITE_SUPABASE_PUBLISHABLE_KEY no frontend.</div> :
    <form onSubmit={submit} className="login-form">
      <label><Mail size={16}/> E-mail<input type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} required placeholder="voce@exemplo.com"/></label>
      <label><LockKeyhole size={16}/> Senha<input type="password" autoComplete={register?'new-password':'current-password'} minLength={6} value={password} onChange={e=>setPassword(e.target.value)} required placeholder="Sua senha"/></label>
      {error&&<div className="alert" role="alert">{error}</div>}
      {message&&<div className="notice" role="status">{message}</div>}
      <button className="primary" disabled={busy}><LogIn size={17}/>{busy?'Processando…':register?'Criar conta':'Entrar'}</button>
      <button className="outline" type="button" onClick={()=>{setRegister(x=>!x);setError('');setMessage('')}}>{register?'Já tenho uma conta':'Criar uma conta'}</button>
    </form>}
    <div className="login-note">Inferência com Ollama local. Login e histórico no Supabase.</div>
  </div></div>
}
