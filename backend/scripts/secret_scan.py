"""Scan repository for likely committed secrets. Never prints secret values."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Categories reported as FOUND / NOT_FOUND — patterns look for key-like material
CATEGORIES: dict[str, list[re.Pattern[str]]] = {
    "openai_key": [
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"OPENAI_API_KEY\s*=\s*['\"]?sk-", re.I),
    ],
    "aws_key": [
        re.compile(r"AKIA[0-9A-Z]{16}"),
    ],
    "private_key_block": [
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ],
    "generic_api_key_assignment": [
        re.compile(
            r"(?:api[_-]?key|secret[_-]?key|webhook[_-]?secret)\s*[:=]\s*['\"][^'\"]{16,}['\"]",
            re.I,
        ),
    ],
    "bearer_token": [
        re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
    ],
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "htmlcov",
}

# Allowlisted substrings (examples / placeholders / test fixtures)
ALLOWLIST_SNIPPETS = (
    "sk-test",
    "sk-example",
    "your-api-key",
    "changeme",
    "placeholder",
    "pg-owner-key",
    "wave4-owner-key",
    "wave1-owner-key",
    "OWNER_API_KEY=",
    "N8N_WEBHOOK_SECRET=",
    'Bearer x',  # redaction unit-test fixture
    "Bearer [REDACTED]",
)


def _iter_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".webp",
                ".ico",
                ".woff",
                ".woff2",
                ".pdf",
                ".zip",
                ".pyc",
            }:
                continue
            files.append(path)
    return files


def _allowlisted(line: str) -> bool:
    lower = line.lower()
    return any(s.lower() in lower for s in ALLOWLIST_SNIPPETS)


def scan(roots: list[Path]) -> dict[str, str]:
    found: dict[str, bool] = {name: False for name in CATEGORIES}
    for path in _iter_files(roots):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            if _allowlisted(line):
                continue
            for cat, patterns in CATEGORIES.items():
                if found[cat]:
                    continue
                for pat in patterns:
                    if pat.search(line):
                        found[cat] = True
                        break
    return {k: ("FOUND" if v else "NOT_FOUND") for k, v in found.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Secret pattern scan (no values printed)")
    parser.add_argument(
        "--root",
        action="append",
        default=None,
        help="Root path to scan (repeatable). Defaults to repo + frontend/dist if present.",
    )
    args = parser.parse_args(argv)

    here = Path(__file__).resolve()
    backend = here.parents[1]
    repo = backend.parent
    defaults = [repo]
    dist = repo / "frontend" / "dist"
    if dist.exists():
        defaults.append(dist)

    roots = [Path(p) for p in args.root] if args.root else defaults
    results = scan(roots)
    any_found = False
    for cat, status in sorted(results.items()):
        print(f"{cat}={status}")
        if status == "FOUND":
            any_found = True
    print(f"DIST_SCANNED={'yes' if (repo / 'frontend' / 'dist').exists() else 'no'}")
    return 1 if any_found else 0


if __name__ == "__main__":
    sys.exit(main())
