"""Run Phase 23 controlled pilot experiment (no auto-send)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings, clear_settings_cache  # noqa: E402
from app.database import get_session_factory, init_db, reset_db_state  # noqa: E402
from app.experiments.phase23.runner import run_phase23_experiment  # noqa: E402
from app.models import Base  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    clear_settings_cache()
    reset_db_state()

    db_path = REPO_ROOT / "experiments" / "phase23" / "phase23.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        app_env="development",
        operating_mode="pilot",
        allow_production_mode=False,
        database_url=f"sqlite+pysqlite:///{db_path.as_posix()}",
        sales_use_ai=False,
        audit_use_ai=False,
        browser_enabled=True,
        browser_javascript_enabled=False,
        max_companies_per_day=20,
        max_audits_per_day=10,
        max_initial_outreach_per_day=5,
        daily_budget_limit=__import__("decimal").Decimal("3.00"),
        max_single_expense=__import__("decimal").Decimal("20.00"),
    )
    engine = init_db(settings, force=True)
    Base.metadata.create_all(bind=engine)
    session = get_session_factory()()
    try:
        report = run_phase23_experiment(
            session,
            settings,
            output_dir=REPO_ROOT / "experiments" / "phase23",
        )
        ceo = report["ceo_report"]
        print("PHASE23_COMPLETE")
        print(f"researched={ceo['companies_researched']}")
        print(f"verified={ceo['companies_verified']}")
        print(f"qualified={ceo['qualified_leads']}")
        print(f"audits={ceo['audits_completed']}")
        print(f"drafts={ceo['outreach_drafts']}")
        print(f"approvals_queued={ceo['approvals_queued']}")
        print(f"report={REPO_ROOT / 'experiments' / 'phase23' / 'CEO_EXPERIMENT_REPORT.md'}")
        return 0
    finally:
        session.close()
        reset_db_state()
        clear_settings_cache()


if __name__ == "__main__":
    raise SystemExit(main())
