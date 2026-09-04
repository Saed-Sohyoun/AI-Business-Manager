"""SystemMode and related enums for owner control plane."""

from __future__ import annotations

import enum


class SystemMode(str, enum.Enum):
    NORMAL = "normal"
    SAFE_MODE = "safe_mode"
    PAUSED_BY_OWNER = "paused_by_owner"


class AlertPriority(str, enum.Enum):
    INFO = "info"
    IMPORTANT = "important"
    URGENT = "urgent"
    CRITICAL = "critical"
