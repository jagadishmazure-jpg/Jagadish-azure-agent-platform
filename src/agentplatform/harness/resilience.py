"""Retry with jittered backoff + circuit breaker. Timeouts and retries live in the harness, not prompts."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class TransientError(RuntimeError):
    """429 / 5xx / timeout — safe to retry."""


class CircuitOpen(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    reset_after_s: float = 30.0
    failures: int = 0
    opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        return time.monotonic() - self.opened_at >= self.reset_after_s  # half-open probe

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        return "half-open" if self.allow() else "open"


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_s: float = 0.05,
    timeout_s: float = 20.0,
    breaker: CircuitBreaker | None = None,
    retry_on: tuple[type[BaseException], ...] = (TransientError, asyncio.TimeoutError, ConnectionError),
) -> tuple[T, int]:
    """Returns (result, retries_used). Raises the last error when attempts are exhausted."""
    last: BaseException | None = None
    for i in range(attempts):
        if breaker and not breaker.allow():
            raise CircuitOpen(breaker.name)
        try:
            result = await asyncio.wait_for(fn(), timeout=timeout_s)
            if breaker:
                breaker.record_success()
            return result, i
        except retry_on as exc:
            last = exc
            if breaker:
                breaker.record_failure()
            if i < attempts - 1:
                await asyncio.sleep(base_delay_s * (2**i) * (0.5 + random.random()))
    assert last is not None
    raise last
