"""Conservative, read-only publication audit for tracked files and Git history.

Prints paths and risk categories only; never prints matching secret values.
This is NOT a replacement for Gitleaks/TruffleHog and manual inspection.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = {
    "GitHub token candidate": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}"),
    "Supabase secret key candidate": re.compile(r"\bsb_secret_[A-Za-z0-9_-]{16,}"),
    "OpenAI API key candidate": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
    "AWS access key candidate": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Private key marker": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "JWT candidate": re.compile(
        r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{10,}\b"
    ),
    "URL with embedded password": re.compile(
        r"(?:postgres(?:ql)?|https?)://[^:/\s@]+:[^/@\s]+@"
    ),
}

PRIVATE_FILENAMES = {".env", ".env.local", ".env.production", ".env.development"}
PRIVATE_SUFFIXES = (".pem", ".p12", ".pfx", ".key")


def risky_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    name = parts[-1].casefold()
    return (
        (name in PRIVATE_FILENAMES or name.startswith(".env."))
        and name not in (".env.example",)
    ) or name.endswith(PRIVATE_SUFFIXES) or name in ("id_rsa", "id_ed25519")


def redacted_findings(text: str, location: str) -> set[tuple[str, str]]:
    """Returns ONLY (location, risk type), never a token or matched substring."""
    return {(location, label) for label, pattern in PATTERNS.items()
            if pattern.search(text)}


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout


def tracked_scan() -> tuple[set[tuple[str, str]], int, int]:
    paths = [p for p in git("ls-files", "-z").split("\0") if p]
    findings: set[tuple[str, str]] = set()
    skipped = 0
    for name in paths:
        if risky_path(name):
            findings.add((name, "Sensitive filename tracked by Git"))
        path = ROOT / name
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                skipped += 1
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped += 1
            continue
        findings.update(redacted_findings(content, name))
    return findings, len(paths), skipped


def history_scan() -> tuple[set[tuple[str, str]], int]:
    # --all scans all locally reachable refs; not remote refs that have not been fetched.
    commits = int(git("rev-list", "--all", "--count").strip() or "0")
    diff = git("log", "--all", "--format=COMMIT:%H", "--patch",
               "--no-ext-diff", "--no-textconv")
    findings: set[tuple[str, str]] = set()
    current = "unknown"
    path = "unknown"
    for line in diff.splitlines():
        if line.startswith("COMMIT:"):
            current = line[7:19]
        elif line.startswith("diff --git a/"):
            # Paths with spaces are displayed approximately; this is a diagnostic only.
            path = line.split(" b/", 1)[-1]
            if risky_path(path):
                findings.add((f"{current}:{path}", "Sensitive filename in history"))
        elif line.startswith("+") and not line.startswith("+++"):
            findings.update(redacted_findings(line[1:], f"{current}:{path}"))
    return findings, commits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracked-only", action="store_true",
                        help="Suitable for shallow-clone CI; skips historical Git revisions")
    args = parser.parse_args()
    try:
        tracked, files, skipped = tracked_scan()
        history: set[tuple[str, str]] = set()
        commits = 0
        if not args.tracked_only:
            history, commits = history_scan()
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"ERRO: auditoria não pôde ser concluída ({type(exc).__name__}).")
        return 2
    findings = sorted(tracked | history)
    print(f"Arquivos Git verificados: {files}; arquivos ignorados por tamanho/formato: {skipped}.")
    if not args.tracked_only:
        print(f"Commits locais examinados: {commits}.")
    if findings:
        print(f"REVISÃO OBRIGATÓRIA: {len(findings)} indício(s), sem revelar valores:")
        for location, label in findings[:40]:
            print(f"- {label}: {location}")
        if len(findings) > 40:
            print(f"... e mais {len(findings) - 40} indícios.")
        return 1
    if skipped:
        print("INCONCLUSIVO: existem arquivos não examinados. Faça inspeção manual.")
        return 2
    print("Nenhum padrão conhecido localizado. Auditoria heurística, não garantia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
