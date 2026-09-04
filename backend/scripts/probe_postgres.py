"""Probe Postgres without printing secrets."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def scheme(url: str) -> str:
    if not url:
        return "MISSING"
    if "://" not in url:
        return "INVALID"
    return url.split("://", 1)[0]


def main() -> None:
    load_dotenv(Path(".env"))
    load_dotenv(Path("backend/.env"))
    url = os.environ.get("DATABASE_URL", "")
    pg = os.environ.get("POSTGRES_TEST_URL", "")
    print("DATABASE_URL_SCHEME=", scheme(url))
    print("POSTGRES_TEST_URL_SCHEME=", scheme(pg))
    candidate = pg or url
    is_pg = scheme(candidate).startswith("postgres")
    print("CANDIDATE_IS_POSTGRES=", is_pg)
    if not is_pg:
        print("POSTGRES_CONNECT=SKIP")
        return
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(candidate, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            version = conn.execute(text("select version()")).scalar()
            conn.execute(text("select 1"))
        print("POSTGRES_CONNECT=OK")
        print("POSTGRES_VERSION_PREFIX=", (version or "")[:50])
    except Exception as exc:  # noqa: BLE001
        print("POSTGRES_CONNECT=FAIL")
        print("POSTGRES_ERROR_TYPE=", type(exc).__name__)
        print("POSTGRES_ERROR_MSG=", str(exc)[:200])


if __name__ == "__main__":
    main()
