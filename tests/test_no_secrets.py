"""
A credential must never reach this repository again.

This exists because one already did. A Supabase `service_role` JWT -- the key
that bypasses Row Level Security entirely -- was committed in
`.streamlit/secrets.toml` and pushed to a public GitHub repo, where it stayed
reachable from `main` long after the file itself was deleted. Deleting a file
does not remove it from history, and the key remained valid for years past the
commit that removed it.

`.gitignore` was already in place and did not prevent it: it matched one exact
path, and the rule only helps for files nobody force-adds. So this runs in CI,
over the files git is actually tracking, and fails the build rather than
trusting anyone to remember.

Scope note: this checks the current working tree, not history. Cleaning history
is a separate one-off operation; this is the guard that stops the next one.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Each pattern is a credential shape that is unambiguous enough not to fire on
# ordinary prose or code. Anything vaguer belongs in review, not in a test that
# blocks the build.
PATTERNS: dict[str, re.Pattern[str]] = {
    "Supabase/JWT token": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "Supabase secret key": re.compile(r"sb_secret_[A-Za-z0-9_-]{10,}"),
    "Supabase publishable key": re.compile(r"sb_publishable_[A-Za-z0-9_-]{10,}"),
    "OpenAI key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Google OAuth client secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

# Placeholders that are supposed to be here. Kept explicit rather than as a
# loose "contains REPLACE_ME" rule, so a real key sitting next to the word
# REPLACE_ME in the same file still fails.
ALLOWED_LITERALS = {
    "sb_publishable_REPLACE_ME",
    "sb_secret_REPLACE_ME",
}

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", "sandbox_data"}
TEXT_SUFFIXES = {
    ".py", ".toml", ".md", ".txt", ".json", ".yml", ".yaml", ".cfg", ".ini",
    ".sql", ".sh", ".js", ".html", ".env", ".example",
}


def tracked_files() -> list[Path]:
    """Only what git actually tracks; ignored files are not our problem here."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        pytest.skip("git not available")
    paths = []
    for name in out.split("\0"):
        if not name:
            continue
        path = ROOT / name
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.is_file():
            paths.append(path)
    return paths


def test_no_credentials_in_tracked_files():
    findings: list[str] = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:  # pragma: no cover
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                if match.group(0) in ALLOWED_LITERALS:
                    continue
                line = text[: match.start()].count("\n") + 1
                findings.append(
                    f"{path.relative_to(ROOT).as_posix()}:{line} looks like a {label}"
                )

    assert not findings, (
        "Possible credentials found in tracked files:\n  "
        + "\n  ".join(findings)
        + "\n\nDo not just delete the line and commit -- git keeps history. Rotate or "
          "deactivate the credential at the provider first, then remove it."
    )


def test_real_secrets_file_is_not_tracked():
    """The specific file that leaked, and its obvious variants."""
    try:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        pytest.skip("git not available")

    offenders = [
        name for name in tracked
        if Path(name).name.startswith("secrets") and not name.endswith(".example")
    ]
    offenders += [name for name in tracked if Path(name).name == ".env"]
    assert not offenders, f"secret-bearing files are tracked by git: {offenders}"


@pytest.mark.parametrize(
    "candidate",
    [
        ".streamlit/secrets.toml",
        ".streamlit/secrets.local.toml",
        "secrets.toml",
        ".env",
        "prod.key",
    ],
)
def test_secret_paths_are_gitignored(candidate: str):
    """
    The ignore rules cover the variants, not just the one path that leaked.

    `git check-ignore` is the authority here rather than reading .gitignore,
    since precedence between patterns is not obvious by inspection.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", candidate], cwd=ROOT, capture_output=True
    )
    assert result.returncode == 0, f"{candidate} is not gitignored"
