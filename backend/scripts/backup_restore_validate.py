"""Validate pg_dump / pg_restore style backup when POSTGRES_TEST_URL is set.

Exit codes:
  0 PASS
  1 FAIL
  2 BLOCKED (POSTGRES_TEST_URL unset)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse, unquote


def _load_dotenv() -> None:
    for candidate in (Path(".env"), Path("backend/.env")):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_pg_url(url: str) -> dict[str, str]:
    normalized = url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )
    parsed = urlparse(normalized)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "dbname": (parsed.path or "/").lstrip("/") or "postgres",
    }


def main() -> int:
    _load_dotenv()
    url = (os.environ.get("POSTGRES_TEST_URL") or "").strip()
    if not url:
        print("BACKUP_RESTORE=BLOCKED")
        print("REASON=POSTGRES_TEST_URL unset")
        return 2

    if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        print("BACKUP_RESTORE=BLOCKED")
        print("REASON=pg_dump/pg_restore not on PATH")
        return 2

    cfg = _parse_pg_url(url)
    env = os.environ.copy()
    if cfg["password"]:
        env["PGPASSWORD"] = cfg["password"]

    with tempfile.TemporaryDirectory(prefix="bos-backup-") as tmp:
        dump_path = Path(tmp) / "dump.dump"
        dump_cmd = [
            "pg_dump",
            "-h",
            cfg["host"],
            "-p",
            cfg["port"],
            "-U",
            cfg["user"],
            "-d",
            cfg["dbname"],
            "-Fc",
            "-f",
            str(dump_path),
        ]
        try:
            subprocess.run(dump_cmd, check=True, env=env, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            print("BACKUP_RESTORE=FAIL")
            print("STAGE=pg_dump")
            print(f"ERROR_TYPE={type(exc).__name__}")
            return 1

        if not dump_path.exists() or dump_path.stat().st_size < 1:
            print("BACKUP_RESTORE=FAIL")
            print("STAGE=pg_dump_empty")
            return 1

        list_cmd = ["pg_restore", "-l", str(dump_path)]
        try:
            subprocess.run(list_cmd, check=True, env=env, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            print("BACKUP_RESTORE=FAIL")
            print("STAGE=pg_restore_list")
            print(f"ERROR_TYPE={type(exc).__name__}")
            return 1

    print("BACKUP_RESTORE=PASS")
    print("NOTE=dump+list validated; no secrets printed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
