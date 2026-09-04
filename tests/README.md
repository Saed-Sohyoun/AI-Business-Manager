# Repository-level test notes

Automated tests live in `backend/tests/`.

```bash
cd backend
python -m pytest -q
```

Phase 21 adds cross-cutting QA in `backend/tests/test_qa_phase21.py` (validation, soft timeout, stale RUNNING reclaim, concurrent finance idempotency, approval/budget, lifespan, E2E manager smoke, frontend format module presence).

Release checklist: [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md).
