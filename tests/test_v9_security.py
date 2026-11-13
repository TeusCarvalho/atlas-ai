"""v9: auth, user isolation, remote persistence — HTTP mocked, no real Supabase account."""
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import api
from backend import auth_store as store

client = TestClient(api.app)
UID_A = str(uuid4())
UID_B = str(uuid4())
ENV = {'SUPABASE_URL': 'https://atlas-test.supabase.co',
       'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_test'}
HEADERS = {'Authorization': 'Bearer test-valid-token'}


@pytest.fixture(autouse=True)
def reset_state():
    api._SESSIONS.clear()
    with patch.dict(os.environ, {'SUPABASE_URL': '', 'SUPABASE_PUBLISHABLE_KEY': ''}):
        yield
    api._SESSIONS.clear()


def test_local_mode_still_available():
    assert client.get('/api/health').json()['authenticated'] is False
    sid = client.post('/api/session').json()['session_id']
    assert len(sid) == 32
    assert client.get('/api/history').json()['runs'] == []


def test_partial_configuration_fails_closed():
    with patch.dict(os.environ, {'SUPABASE_URL': ENV['SUPABASE_URL'], 'SUPABASE_PUBLISHABLE_KEY': ''}):
        assert client.post('/api/session').status_code == 503
        assert client.get('/api/health').status_code == 503


def test_remote_requires_login_even_for_upload_related_endpoints():
    with patch.dict(os.environ, ENV):
        assert client.post('/api/session').status_code == 401
        assert client.post('/api/data/summary', json={'session_id':'a'*32}).status_code == 401
        assert client.post('/api/analyze', json={'session_id':'a'*32,'meses':60,'horizonte':3}).status_code == 401
        assert client.get('/api/history').status_code == 401


def test_remote_rejects_bad_token():
    with patch.dict(os.environ, ENV):
        with patch.object(store.httpx, 'get', return_value=httpx.Response(401)):
            response = client.post('/api/session', headers=HEADERS)
        assert response.status_code == 401


def test_remote_auth_service_down_fails_closed():
    with patch.dict(os.environ, ENV):
        with patch.object(store.httpx, 'get', side_effect=httpx.ConnectError('network')):
            response = client.post('/api/session', headers=HEADERS)
        assert response.status_code == 503


def test_remote_sessions_owned_by_auth_user():
    with patch.dict(os.environ, ENV):
        with patch.object(store.httpx, 'get', return_value=httpx.Response(200,json={'id':UID_A})), \
             patch.object(api, 'list_messages', return_value=[]):
            response = client.post('/api/session', headers=HEADERS)
        assert response.status_code == 200
        sid = response.json()['session_id']
        assert api.session_for(sid, UID_A)[1].user_id == UID_A
        with pytest.raises(Exception) as error:
            api.session_for(sid, UID_B)
        assert error.value.status_code == 403


def test_save_run_uses_verified_identity_not_user_supplied():
    actor = store.Actor(UID_A, 'tokenA', True)
    with patch.object(store, '_rest') as rest:
        store.insert_run(actor, 'economia', 'Teste', 'Resumo', {'painel': {}})
    args, kwargs = rest.call_args
    assert args[:3] == (actor, 'atlas_runs', 'POST')
    assert kwargs['records']['user_id'] == UID_A


def test_history_select_limited_to_verified_user():
    actor = store.Actor(UID_A, 'tokenA', True)
    with patch.object(store, '_rest', return_value=[]) as rest:
        assert store.list_runs(actor) == []
    assert rest.call_args.kwargs['params']['user_id'] == f'eq.{UID_A}'


def test_history_rejects_invalid_uuid():
    with pytest.raises(Exception) as exc:
        store.read_run(store.Actor(UID_A, 'tokenA', True), 'garbage')
    assert exc.value.status_code == 422


def test_restore_history_into_context():
    with patch.dict(os.environ, ENV):
        saved = [
            {'channel':'assistente','role':'user','body':'Quanto é 2 + 2?'},
            {'channel':'assistente','role':'assistant','body':'4'},
            {'channel':'dados','role':'user','body':'Qual a receita?'},
        ]
        with patch.object(store.httpx, 'get', return_value=httpx.Response(200,json={'id':UID_A})), \
             patch.object(api, 'list_messages', return_value=saved):
            r = client.post('/api/session', headers=HEADERS)
        assert r.status_code == 200
        ctx = api.session_for(r.json()['session_id'], UID_A)[1].context
        assert [m['content'] for m in ctx.historico] == ['Quanto é 2 + 2?', '4']


def test_messages_persist_both_roles_and_order():
    actor = store.Actor(UID_A, 'tokenA', True)
    with patch.object(store, '_rest') as rest:
        store.insert_messages(actor, 'assistente', 'Pergunta', 'Resposta', [{'ferramenta': 'abc'}])
    rows = rest.call_args.kwargs['records']
    assert [r['role'] for r in rows] == ['user','assistant']
    assert rows[0]['created_at'] < rows[1]['created_at']
    assert all(row['user_id'] == UID_A for row in rows)


def test_schema_has_owner_rls_for_both_tables():
    sql = (Path(__file__).resolve().parents[1] / 'supabase' / 'schema.sql').read_text().lower()
    for table in ['atlas_runs', 'atlas_messages']:
        assert f'alter table public.{table} enable row level security' in sql
        assert sql.count('auth.uid()') >= 4
        assert 'with check' in sql
    assert 'service_role' not in (Path(__file__).resolve().parents[1] / 'backend' / 'auth_store.py').read_text()
