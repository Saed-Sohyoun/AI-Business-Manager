"""Provider smoke checks — config-only or safe test inbox. Never cold outreach."""

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
    # Import after env so Settings sees keys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.config import Settings

    settings = Settings()
    results: list[tuple[str, str]] = []

    results.append(("openai", "CONFIGURED" if settings.openai_configured else "SKIP"))
    results.append(("tavily", "CONFIGURED" if settings.tavily_configured else "SKIP"))
    results.append(("telegram", "CONFIGURED" if settings.telegram_configured else "SKIP"))

    # Email: never send cold outreach. Only config check unless OWNER_TEST_INBOX set.
    test_inbox = (os.environ.get("OWNER_TEST_INBOX") or "").strip()
    if not settings.resend_configured:
        results.append(("email", "SKIP"))
    elif not test_inbox:
        results.append(("email", "CONFIG_ONLY"))
        print("EMAIL_NOTE=no OWNER_TEST_INBOX — skipping send (safe)")
    else:
        # Verified test inbox path: still do not send unless explicitly allowed
        allow_send = (os.environ.get("OWNER_TEST_EMAIL_SEND") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if not allow_send:
            results.append(("email", "CONFIG_ONLY"))
            print("EMAIL_NOTE=OWNER_TEST_INBOX set but OWNER_TEST_EMAIL_SEND not true — no send")
        else:
            # Soft validation only — do not call Resend in default smoke
            results.append(("email", "CONFIGURED_TEST_INBOX"))
            print("EMAIL_NOTE=send not performed by default smoke (set explicit runner for live)")

    for name, status in results:
        print(f"{name}={status}")

    # Exit 0 even when skipped — smoke is informational; misconfig is not a secret leak
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
