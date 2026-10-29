import logging
import threading
import time
from typing import Protocol

SECONDS_PER_MINUTE = 60
PROGRESS_REPORTS = 10


class Clock(Protocol):
    def now(self) -> float: ...


class ProgressSink(Protocol):
    """Where the pipeline and the renderer report progress: the terminal or a web job."""

    def stage(self, position: str, label: str) -> None: ...

    def start_task(self) -> None: ...

    def step(self, done: int, total: int) -> None: ...


class MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


class DurationText:
    def format(self, seconds: float) -> str:
        if seconds < SECONDS_PER_MINUTE:
            return "menos de 1 min"
        return f"~{round(seconds / SECONDS_PER_MINUTE)} min"


class ProgressReporter:
    """Prints progress in Portuguese. The time left comes from the pace measured so far."""

    def __init__(self, logger: logging.Logger, clock: Clock, lock: threading.Lock) -> None:
        self._logger = logger
        self._clock = clock
        self._lock = lock
        self._started = 0.0

    @classmethod
    def create(cls, logger: logging.Logger) -> "ProgressReporter":
        return cls(logger, MonotonicClock(), threading.Lock())

    def stage(self, position: str, label: str) -> None:
        self.start_task()
        self._logger.info("[%s] %s", position, label)

    def start_task(self) -> None:
        self._started = self._clock.now()

    def step(self, done: int, total: int) -> None:
        """Logs about ten times per task, not once per item."""
        if done % max(1, total // PROGRESS_REPORTS) and done != total:
            return
        with self._lock:
            elapsed = self._clock.now() - self._started
            left = elapsed / done * (total - done) if done else 0.0
            self._logger.info("    %s de %s (faltam %s)", done, total, DurationText().format(left))
