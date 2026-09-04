"""Alembic upgrade/downgrade against POSTGRES_TEST_URL.

Exit codes:
  0 PASS
  1 FAIL
  2 BLOCKED (POSTGRES_TEST_URL unset)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


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


def main() -> int:
    _load_dotenv()
    url = (os.environ.get("POSTGRES_TEST_URL") or "").strip()
    if not url:
        print("MIGRATIONS_POSTGRES=BLOCKED")
        print("REASON=POSTGRES_TEST_URL unset")
        return 2

    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    os.environ["DATABASE_URL"] = url

    try:
        from alembic import command
        from alembic.config import Config
        from app.config import clear_settings_cache

        clear_settings_cache()
        cfg = Config(str(backend / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", url)
        print("MIGRATIONS_POSTGRES=RUNNING")
        command.upgrade(cfg, "head")
        # Downgrade one revision then re-upgrade to validate Wave 5 migration
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "head")
        print("MIGRATIONS_POSTGRES=PASS")
        return 0
    except Exception as exc:  # noqa: BLE001
        print("MIGRATIONS_POSTGRES=FAIL")
        print(f"ERROR_TYPE={type(exc).__name__}")
        print(f"ERROR_MSG={str(exc)[:200]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
