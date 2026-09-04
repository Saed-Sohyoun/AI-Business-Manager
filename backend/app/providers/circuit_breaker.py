"""Provider circuit breaker — CLOSED / OPEN / HALF_OPEN."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

from app.exceptions import ServiceUnavailableError

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    reset_timeout_seconds: float = 30.0
    half_open_successes: int = 1
    _state: CircuitState = CircuitState.CLOSED
    _failures: int = 0
    _opened_at: float | None = None
    _half_open_ok: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_half_open()
            return self._state

    def _maybe_half_open(self) -> None:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.reset_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_ok = 0

    def allow_request(self) -> bool:
        with self._lock:
            self._maybe_half_open()
            if self._state == CircuitState.OPEN:
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_ok += 1
                if self._half_open_ok >= self.half_open_successes:
                    self._state = CircuitState.CLOSED
                    self._failures = 0
                    self._opened_at = None
            else:
                self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state == CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def call(self, fn: Callable[[], T]) -> T:
        if not self.allow_request():
            raise ServiceUnavailableError(
                f"{self.name} is temporarily unavailable",
                details={"code": "CIRCUIT_OPEN", "provider": self.name},
            )
        try:
            result = fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self._failures,
        }


_REGISTRY: dict[str, CircuitBreaker] = {}
_REG_LOCK = threading.Lock()


def get_circuit(name: str, **kwargs: Any) -> CircuitBreaker:
    with _REG_LOCK:
        if name not in _REGISTRY:
            _REGISTRY[name] = CircuitBreaker(name=name, **kwargs)
        return _REGISTRY[name]


def reset_circuits() -> None:
    with _REG_LOCK:
        _REGISTRY.clear()


def all_circuit_snapshots() -> list[dict[str, Any]]:
    with _REG_LOCK:
        return [c.snapshot() for c in _REGISTRY.values()]
