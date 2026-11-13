"""Regressões de segurança e instalação identificadas na auditoria v12."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def test_fresh_schema_accepts_research_channel():
    sql = (ROOT / "supabase/schema.sql").read_text(encoding="utf-8").lower()
    assert "channel in ('assistente', 'dados', 'research')" in sql
    assert "drop constraint if exists atlas_messages_channel_check" in sql
    assert "add constraint atlas_messages_channel_check" in sql


def test_all_user_data_tables_have_rls_in_schema_files():
    basic = (ROOT / "supabase/schema.sql").read_text(encoding="utf-8").lower()
    rag = (ROOT / "supabase/rag_v10.sql").read_text(encoding="utf-8").lower()
    for table in ("atlas_runs", "atlas_messages"):
        assert f"alter table public.{table} enable row level security" in basic
    for table in ("atlas_documents", "atlas_chunks"):
        assert f"alter table public.{table} enable row level security" in rag
    assert "security invoker" in rag


def test_vite_has_security_backport():
    p = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    version = p["devDependencies"]["vite"]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    assert match, "Fixar a versão do Vite sem intervalos"
    major, minor, patch = map(int, match.groups())
    assert major != 6 or (minor, patch) >= (4, 6), "Vite 6 exige versão 6.4.6 ou superior"
    assert major >= 6


def test_frontend_server_only_listens_loopback():
    config = (ROOT / "frontend/vite.config.js").read_text(encoding="utf-8")
    assert "host: '127.0.0.1'" in config
    script = (ROOT / "start_api_windows.ps1").read_text(encoding="utf-8")
    assert "--host 127.0.0.1" in script


def test_secrets_ignored_before_git_publication():
    rootignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in rootignore
    assert "frontend/.env*" in rootignore
    assert "frontend/node_modules/" in rootignore
