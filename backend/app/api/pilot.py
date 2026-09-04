"""Pilot Mode status API — read-only visibility for operators."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.middleware.request_id import get_request_id
from app.pilot.execution import ExecutionGuard
from app.pilot.schemas import PilotStatus
from app.schemas.common import DataResponse

router = APIRouter(prefix="/pilot", tags=["pilot"])


def _settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


@router.get("/status", response_model=DataResponse[PilotStatus])
def pilot_status(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> DataResponse[PilotStatus]:
    """Current Pilot Mode envelope, usage, and budget (source of truth: backend)."""
    cfg = _settings(request)
    status = ExecutionGuard(session, cfg).status()
    return DataResponse(data=status, request_id=get_request_id(request))
