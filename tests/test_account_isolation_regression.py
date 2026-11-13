"""Security regressions for cross-account access without real credentials.

These tests validate the Atlas API/session checks and request scoping.
They do NOT replace end-to-end RLS tests against two Supabase accounts.
"""
from uuid import uuid4
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import api, auth_store, research


@pytest.fixture
def actors():
    return (
        auth_store.Actor(str(uuid4()), "jwt-test-a", True),
        auth_store.Actor(str(uuid4()), "jwt-test-b", True),
    )


@pytest.fixture
def clean_api():
    api._SESSIONS.clear()
    api.app.dependency_overrides.clear()
    yield
    api.app.dependency_overrides.clear()
    api._SESSIONS.clear()


def test_cross_account_session_rejected_before_execution(actors, clean_api):
    owner, intruder = actors
    session_id, _ = api.session_for(None, owner.user_id)
    api.app.dependency_overrides[api.require_actor] = lambda: intruder
    client = TestClient(api.app)
    with patch.object(api, "executar_pedido") as mocked_model:
        response = client.post("/api/chat", json={
            "session_id": session_id, "pergunta": "Acesse o contexto da outra conta"
        })
    assert response.status_code == 403
    mocked_model.assert_not_called()
    assert client.post("/api/data/summary", json={"session_id": session_id}).status_code == 403
    assert client.post("/api/session/clear", json={"session_id": session_id}).status_code == 403


def test_owner_can_use_own_session(actors, clean_api):
    owner, _ = actors
    session_id, _ = api.session_for(None, owner.user_id)
    api.app.dependency_overrides[api.require_actor] = lambda: owner
    response = TestClient(api.app).post("/api/session/clear", json={"session_id": session_id})
    assert response.status_code == 200


def test_history_lookup_scopes_both_record_and_user(actors):
    owner, intruder = actors
    record_id = str(uuid4())
    with patch.object(auth_store, "_rest", return_value=[]) as remote:
        assert auth_store.read_run(intruder, record_id) is None
    assert remote.call_args.args[:3] == (intruder, "atlas_runs", "GET")
    assert remote.call_args.kwargs["params"]["id"] == f"eq.{record_id}"
    assert remote.call_args.kwargs["params"]["user_id"] == f"eq.{intruder.user_id}"
    assert owner.user_id not in str(remote.call_args.kwargs)


def test_message_and_run_lists_scope_by_verified_user(actors):
    _, intruder = actors
    with patch.object(auth_store, "_rest", return_value=[]) as remote:
        auth_store.list_runs(intruder)
        first = remote.call_args.kwargs["params"]
        auth_store.list_messages(intruder)
        second = remote.call_args.kwargs["params"]
    assert first["user_id"] == f"eq.{intruder.user_id}"
    assert second["user_id"] == f"eq.{intruder.user_id}"


def test_document_reads_and_deletes_scope_by_owner(actors):
    _, intruder = actors
    doc_id = str(uuid4())
    with patch.object(research, "_remote", return_value=[]) as remote:
        assert research.list_documents(intruder) == []
        assert remote.call_args.kwargs["params"]["user_id"] == f"eq.{intruder.user_id}"
        with pytest.raises(HTTPException) as exc:
            research.delete_document(intruder, doc_id)
    assert exc.value.status_code == 404
    assert remote.call_args.kwargs["params"]["id"] == f"eq.{doc_id}"
    assert remote.call_args.kwargs["params"]["user_id"] == f"eq.{intruder.user_id}"


def test_vector_search_uses_user_jwt_without_privileged_key(actors):
    _, actor = actors
    with patch.object(research, "settings", return_value=(
        "https://example.supabase.co", "sb_publishable_test"
    )), patch.object(research.httpx, "request", return_value=httpx.Response(200, json=[])) as request:
        result = research._remote(actor, "rpc/match_atlas_chunks", "POST", data={
            "query_embedding": [0.0], "match_count": 1, "filter_document_id": None
        })
    assert result == []
    assert request.call_args.kwargs["headers"]["Authorization"] == f"Bearer {actor.token}"
    assert request.call_args.kwargs["headers"]["apikey"] == "sb_publishable_test"


def test_rag_rpc_is_security_invoker_with_user_filter():
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[1] / "supabase" / "rag_v10.sql").read_text(encoding="utf-8").lower()
    assert "security invoker" in sql
    assert "auth.uid()" in sql
    assert "match_atlas_chunks" in sql
