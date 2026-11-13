"""Supabase Auth + PostgREST with end-user JWTs. No privileged keys.

When both environment values are absent, development-only local mode remains.
If either setting is present, missing configuration must fail closed.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from urllib.parse import urlsplit

import httpx
from fastapi import Header, HTTPException


def settings() -> tuple[str, str] | None:
    url = os.getenv('SUPABASE_URL', '').strip().rstrip('/')
    key = os.getenv('SUPABASE_PUBLISHABLE_KEY', '').strip()
    if bool(url) != bool(key):
        raise HTTPException(503, 'Supabase parcialmente configurado: configure URL e publishable key.')
    if not url:
        return None
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.supabase.co')
            or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment or parsed.path):
        raise HTTPException(503, 'SUPABASE_URL deve ser a URL HTTPS oficial do projeto Supabase.')
    return url, key


@dataclass(frozen=True)
class Actor:
    user_id: str
    token: str | None
    remote: bool


def require_actor(authorization: str | None = Header(default=None)) -> Actor:
    conf = settings()
    if conf is None:
        return Actor(user_id='local', token=None, remote=False)
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Faça login para utilizar o Atlas Agent.')
    token = authorization[7:].strip()
    if not token or len(token) > 8192:
        raise HTTPException(401, 'Token de acesso ausente ou inválido.')
    url, key = conf
    try:
        response = httpx.get(
            f'{url}/auth/v1/user',
            headers={'apikey': key, 'Authorization': f'Bearer {token}'},
            timeout=8.0,
        )
    except httpx.RequestError as exc:
        raise HTTPException(503, 'Serviço de autenticação indisponível.') from exc
    if response.status_code in (401, 403):
        raise HTTPException(401, 'Sessão expirada ou inválida. Entre novamente.')
    if response.status_code != 200:
        raise HTTPException(503, 'Não foi possível validar a sessão no Supabase.')
    payload = response.json()
    try:
        uid = str(UUID(payload['id']))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(401, 'Identidade inválida.') from exc
    return Actor(uid, token, True)


def _rest(actor: Actor, table: str, method: str, *, params: dict | None = None,
          records: Any = None) -> Any:
    if not actor.remote:
        return []
    conf = settings()
    if conf is None or actor.token is None:
        raise HTTPException(503, 'Supabase não está configurado.')
    url, key = conf
    if table not in {'atlas_runs', 'atlas_messages'}:
        raise ValueError('Tabela não permitida.')
    headers = {'apikey': key, 'Authorization': f'Bearer {actor.token}',
               'Accept': 'application/json'}
    if method == 'POST':
        headers.update({'Content-Type': 'application/json', 'Prefer': 'return=minimal'})
    try:
        response = httpx.request(method, f'{url}/rest/v1/{table}',
                                 headers=headers, params=params, json=records,
                                 timeout=10.0)
    except httpx.RequestError as exc:
        raise HTTPException(503, 'Banco de dados temporariamente indisponível.') from exc
    if response.status_code in (401, 403):
        raise HTTPException(403, 'Permissão negada pelo Supabase. Verifique as políticas RLS.')
    if response.status_code >= 400:
        raise HTTPException(502, f'Falha ao persistir no Supabase (HTTP {response.status_code}). Confira o SQL de instalação.')
    return response.json() if method == 'GET' else None


def insert_run(actor: Actor, category: str, title: str, summary: str, payload: dict):
    if actor.remote:
        _rest(actor, 'atlas_runs', 'POST', records={
            'user_id': actor.user_id, 'category': category, 'title': title[:160],
            'summary': summary[:1200], 'payload': payload,
        })


def insert_messages(actor: Actor, channel: str, question: str, answer: str, tools: list):
    if actor.remote:
        timestamp = datetime.now(timezone.utc)
        rows = [
            {'user_id': actor.user_id, 'channel': channel, 'role': 'user',
             'body': question[:2000], 'tools': [], 'created_at': timestamp.isoformat()},
            {'user_id': actor.user_id, 'channel': channel, 'role': 'assistant',
             'body': answer[:10000], 'tools': tools[:12],
             'created_at': (timestamp + timedelta(milliseconds=1)).isoformat()},
        ]
        _rest(actor, 'atlas_messages', 'POST', records=rows)


def list_runs(actor: Actor) -> list[dict]:
    return _rest(actor, 'atlas_runs', 'GET', params={
        'select': 'id,category,title,summary,created_at',
        'user_id': f'eq.{actor.user_id}', 'order': 'created_at.desc', 'limit': '30',
    })


def read_run(actor: Actor, run_id: str) -> dict | None:
    try:
        normalized = str(UUID(run_id))
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, 'Identificador inválido.') from exc
    result = _rest(actor, 'atlas_runs', 'GET', params={
        'select': 'id,category,title,summary,created_at,payload',
        'id': f'eq.{normalized}', 'user_id': f'eq.{actor.user_id}', 'limit': '1',
    })
    return result[0] if result else None


def list_messages(actor: Actor, limit: int = 60) -> list[dict]:
    result = _rest(actor, 'atlas_messages', 'GET', params={
        'select': 'channel,role,body,tools,created_at',
        'user_id': f'eq.{actor.user_id}', 'order': 'created_at.desc',
        'limit': str(min(max(limit, 1), 100)),
    })
    return list(reversed(result))
