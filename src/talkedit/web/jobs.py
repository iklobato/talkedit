import dataclasses
import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, ClassVar

from talkedit.errors import BusyError, TalkeditError
from talkedit.progress import Clock, ProgressReporter


class JobKind(Enum):
    EDIT = "editar"
    PREVIEW = "previa"
    RENDER = "aprovar"
    REDO = "refazer"


class JobPhase(Enum):
    IDLE = "parado"
    RUNNING = "rodando"
    DONE = "pronto"
    FAILED = "erro"


@dataclass(frozen=True)
class JobSnapshot:
    """What the page shows about the one job that may be running."""

    kind: JobKind | None = None
    project_key: str = ""
    phase: JobPhase = JobPhase.IDLE
    stage_label: str = ""
    detail: str = ""
    started: float = 0.0
    finished: float = 0.0
    error_message: str = ""
    error_hint: str = ""

    def is_running(self) -> bool:
        return self.phase is JobPhase.RUNNING

    def runs_on(self, key: str) -> bool:
        return self.is_running() and self.project_key == key


@dataclass(frozen=True)
class JobRequest:
    kind: JobKind
    project_key: str
    work: Callable[[], None]


class JobTracker:
    """Runs one job at a time in a background thread and keeps its latest snapshot.
    An unexpected crash still ends as FAILED (in `finally`), so the page never waits
    forever; the traceback goes to the terminal through the thread hook."""

    CRASH_MESSAGE: ClassVar[str] = "O trabalho parou com um erro inesperado."
    CRASH_HINT: ClassVar[str] = "Veja a mensagem no Terminal onde voce rodou talkedit abrir."

    def __init__(self, clock: Clock, lock: threading.Lock, snapshot: JobSnapshot) -> None:
        self._clock = clock
        self._lock = lock
        self._snapshot = snapshot

    @classmethod
    def create(cls, clock: Clock) -> "JobTracker":
        return cls(clock, threading.Lock(), JobSnapshot())

    def snapshot(self) -> JobSnapshot:
        with self._lock:
            return self._snapshot

    def start(self, request: JobRequest) -> None:
        with self._lock:
            if self._snapshot.is_running():
                raise BusyError(
                    "Ja tem um video sendo processado.",
                    "Espere ele terminar; o talkedit faz um video por vez.",
                )
            self._snapshot = JobSnapshot(
                request.kind, request.project_key, JobPhase.RUNNING, started=self._clock.now()
            )
        threading.Thread(target=self._run, args=(request.work,), daemon=True).start()

    def show_stage(self, label: str) -> None:
        with self._lock:
            self._snapshot = dataclasses.replace(self._snapshot, stage_label=label, detail="")

    def show_project(self, key: str) -> None:
        """A Drive link only becomes a project after the download."""
        with self._lock:
            self._snapshot = dataclasses.replace(self._snapshot, project_key=key)

    def show_detail(self, detail: str) -> None:
        with self._lock:
            self._snapshot = dataclasses.replace(self._snapshot, detail=detail)

    def _run(self, work: Callable[[], None]) -> None:
        try:
            work()
            self._finish(JobPhase.DONE, "", "")
        except TalkeditError as error:
            self._finish(JobPhase.FAILED, error.message, error.hint)
        finally:
            if self.snapshot().is_running():
                self._finish(JobPhase.FAILED, self.CRASH_MESSAGE, self.CRASH_HINT)

    def _finish(self, phase: JobPhase, message: str, hint: str) -> None:
        with self._lock:
            self._snapshot = dataclasses.replace(
                self._snapshot,
                phase=phase,
                error_message=message,
                error_hint=hint,
                finished=self._clock.now(),
            )


class JobProgress:
    """ProgressSink for a web job: keeps the terminal log and tells the tracker which
    stage runs and how far a long task is."""

    def __init__(self, tracker: JobTracker, terminal: ProgressReporter) -> None:
        self._tracker = tracker
        self._terminal = terminal

    def stage(self, position: str, label: str) -> None:
        self._terminal.stage(position, label)
        self._tracker.show_stage(label)

    def start_task(self) -> None:
        self._terminal.start_task()

    def step(self, done: int, total: int) -> None:
        self._tracker.show_detail(f"{done} de {total}")
        self._terminal.step(done, total)


class JobLogHandler(logging.Handler):
    """Copies each progress line (Drive download, render) into the job's detail."""

    def __init__(self, tracker: JobTracker) -> None:
        super().__init__()
        self._tracker = tracker

    def emit(self, record: logging.LogRecord) -> None:
        if self._tracker.snapshot().is_running():
            self._tracker.show_detail(record.getMessage().strip())
