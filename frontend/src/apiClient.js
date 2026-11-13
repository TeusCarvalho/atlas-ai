import {supabase} from './supabase.js'

export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (supabase) {
    const {data, error} = await supabase.auth.getSession()
    if (error || !data.session?.access_token) throw Error('Sessão expirada. Faça login novamente.')
    headers.set('Authorization', `Bearer ${data.session.access_token}`)
  }
  return fetch(`/api${path}`, {...options, headers})
}

export async function apiPost(path, body) {
  const response = await apiFetch(path, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body ?? {}),
  })
  const json = await response.json().catch(() => ({}))
  if (!response.ok) throw Error(typeof json.detail === 'string' ? json.detail : `HTTP ${response.status}`)
  return json
}

export async function apiGet(path) {
  const response = await apiFetch(path)
  const json = await response.json().catch(() => ({}))
  if (!response.ok) throw Error(typeof json.detail === 'string' ? json.detail : `HTTP ${response.status}`)
  return json
}
