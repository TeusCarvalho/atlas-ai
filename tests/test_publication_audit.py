"""Regressões da auditoria de publicação; não incluem credenciais reais."""
from scripts import audit_publication as audit


def test_sensitive_filenames_are_rejected():
    assert audit.risky_path(".env")
    assert audit.risky_path("frontend/.env.local")
    assert audit.risky_path("config/private.key")
    assert audit.risky_path("id_rsa")
    assert not audit.risky_path(".env.example")
    assert not audit.risky_path("frontend/.env.example")
    assert not audit.risky_path("README.md")


def test_detected_secret_values_are_never_returned():
    fake = "ghp_" + "A" * 32
    findings = audit.redacted_findings("export TOKEN=" + fake, "arquivo.py")
    assert findings == {("arquivo.py", "GitHub token candidate")}
    assert fake not in repr(findings)


def test_mocks_detect_explicit_supabase_and_private_key_signatures():
    fake = "sb_secret_" + "Z" * 32
    findings = audit.redacted_findings(fake, "arquivo.py")
    assert ("arquivo.py", "Supabase secret key candidate") in findings
    assert audit.redacted_findings("-----BEGIN PRIVATE KEY-----", "p.pem")


def test_example_values_are_not_mistaken_for_real_secrets():
    assert not audit.redacted_findings("SUPABASE_PUBLISHABLE_KEY=sb_publishable_SEU_VALOR", "env.example")
    assert not audit.redacted_findings("SUPABASE_URL=https://example.supabase.co", "env.example")
