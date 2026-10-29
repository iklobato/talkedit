import logging
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ClassVar, Protocol

from talkedit.app import ProjectAssembler
from talkedit.drive import VideoSource
from talkedit.errors import BusyError, MediaError, ProjectError
from talkedit.plan import TimeRange
from talkedit.plan_changes import PlanChanges
from talkedit.progress import ProgressReporter
from talkedit.projects import OpenProject, ProjectKey, ProjectOpener, ProjectRegistry
from talkedit.render import RenderProfile
from talkedit.settings_writer import SettingsStore
from talkedit.web.http import Readable
from talkedit.web.jobs import JobKind, JobProgress, JobRequest, JobTracker
from talkedit.workspace import ProjectState, ProjectStateStore, ProjectWorkspace, RunMode, Stage


class FolderOpener(Protocol):
    def reveal(self, folder: Path) -> None: ...


class FinderOpener:
    def reveal(self, folder: Path) -> None:
        os.system(f"open {shlex.quote(str(folder))} > /dev/null 2>&1")


@dataclass(frozen=True)
class WebServices:
    assembler: ProjectAssembler
    registry: ProjectRegistry
    settings: SettingsStore
    sources: VideoSource
    jobs: JobTracker
    logger: logging.Logger


class OpenerFactory:
    def __init__(self, services: WebServices) -> None:
        self._services = services

    def for_job(self) -> ProjectOpener:
        services = self._services
        progress = JobProgress(services.jobs, ProgressReporter.create(services.logger))
        return ProjectOpener(services.assembler, progress, services.registry)

    def for_read(self) -> ProjectOpener:
        services = self._services
        return ProjectOpener(
            services.assembler, ProgressReporter.create(services.logger), services.registry
        )


@dataclass(frozen=True)
class NewVideo:
    source: str
    mode: RunMode
    style: str


class EditJobs:
    """Every long action runs as the one background job."""

    def __init__(self, services: WebServices, openers: OpenerFactory) -> None:
        self._services = services
        self._openers = openers

    def start_new(self, video: NewVideo) -> None:
        """The project key is announced only once the project exists on disk, so the page
        never asks for a project that is not registered yet."""
        self._start(JobKind.EDIT, "", lambda: self._edit_new(video))

    def resume(self, key: str) -> None:
        self._start(JobKind.EDIT, key, lambda: self._run_to_end(key))

    def preview(self, key: str) -> None:
        self._start(JobKind.PREVIEW, key, lambda: self._preview(key))

    def approve(self, key: str) -> None:
        self._start(JobKind.RENDER, key, lambda: self._approve(key))

    def redo(self, key: str, request: str) -> None:
        self._start(JobKind.REDO, key, lambda: self._redo(key, request))

    def _start(self, kind: JobKind, key: str, work: Callable[[], None]) -> None:
        self._services.jobs.start(JobRequest(kind, key, work))

    def _edit_new(self, video: NewVideo) -> None:
        source = self._services.sources.local_path(video.source, None)
        workspace = ProjectWorkspace.beside(source)
        store = ProjectStateStore(workspace)
        overrides = [f"estilo={video.style}"] if video.style else []
        state = (
            store.load()
            if store.exists()
            else ProjectState(source=str(source), mode=video.mode, overrides=overrides)
        )
        project = self._openers.for_job().open_state(workspace, state)
        store.save(state)
        self._services.jobs.show_project(ProjectKey.of(workspace.root).value)
        project.services.pipeline.run_until(project.context, Stage.REVIEW)

    def _run_to_end(self, key: str) -> None:
        project = self._openers.for_job().open(self._services.registry.find(key))
        last = Stage.RENDER if project.state.approved else Stage.REVIEW
        project.services.pipeline.run_until(project.context, last)

    def _preview(self, key: str) -> None:
        project = self._openers.for_job().open(self._services.registry.find(key))
        target = project.context.workspace.preview_video
        project.services.renderer.render(project.context, RenderProfile.preview(), target)

    def _approve(self, key: str) -> None:
        workspace = self._services.registry.find(key)
        store = ProjectStateStore(workspace)
        store.save(store.load().approve())
        self._run_to_end(key)

    def _redo(self, key: str, request: str) -> None:
        workspace = self._services.registry.find(key)
        store = ProjectStateStore(workspace)
        reopened = store.load().reopen_from(Stage.PLAN)
        store.save(reopened.model_copy(update={"editor_request": request.strip()}))
        self._run_to_end(key)



class PlanEditing:
    """Instant changes from the review page. They are refused while a job runs on the
    same project, and they cancel an approval, because the old video no longer matches."""

    def __init__(self, services: WebServices, openers: OpenerFactory, changes: PlanChanges) -> None:
        self._services = services
        self._openers = openers
        self._changes = changes

    def give_back(self, key: str, cut_id: str) -> None:
        context = self._open(key).context
        context.plans.save(self._changes.give_back(context.plans.load(), cut_id))

    def apply(self, key: str, cut_id: str) -> None:
        context = self._open(key).context
        context.plans.save(self._changes.apply(context.plans.load(), cut_id))

    def mark(self, key: str, span: TimeRange) -> None:
        context = self._open(key).context
        plan = self._changes.mark(context.plans.load(), context.transcripts.load(), span)
        context.plans.save(plan)

    def _open(self, key: str) -> OpenProject:
        if self._services.jobs.snapshot().runs_on(key):
            raise BusyError("Esse video esta sendo processado agora.", "Espere a etapa terminar.")
        workspace = self._services.registry.find(key)
        store = ProjectStateStore(workspace)
        state = store.load()
        if not state.is_done(Stage.REVIEW):
            raise ProjectError("O plano ainda nao esta pronto.", "Espere a IA revisora terminar.")
        if state.approved:
            store.save(state.reopen_from(Stage.RENDER))
        return self._openers.for_read().open(workspace)



class VideoUploads:
    """Saves a dragged video into the videos folder. The browser never tells the page a
    file's path, so the bytes are copied; a name already used gets a number."""

    EXTENSIONS: ClassVar[frozenset[str]] = frozenset(
        {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
    )
    UNSAFE: ClassVar[re.Pattern[str]] = re.compile(r"[^\w.\- ]")
    CHUNK_BYTES: ClassVar[int] = 1024 * 1024

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def save(self, name: str, body: Readable, length: int) -> Path:
        target = self._free_name(self._clean(name))
        partial = target.with_name(f".{target.name}.parcial")
        with partial.open("wb") as output:
            left = length
            for chunk in iter(lambda: body.read(min(self.CHUNK_BYTES, left)), b""):
                output.write(chunk)
                left -= len(chunk)
        if left:
            partial.unlink(missing_ok=True)
            raise MediaError("O envio do video foi interrompido.", "Arraste o video de novo.")
        return partial.replace(target)

    def _clean(self, name: str) -> str:
        cleaned = self.UNSAFE.sub("_", Path(name).name).strip(" .")
        if Path(cleaned).suffix.lower() not in self.EXTENSIONS:
            raise ProjectError(
                f"{name} nao parece um video.",
                "Use um arquivo .mp4, .mov, .m4v, .mkv, .webm ou .avi.",
            )
        return cleaned

    def _free_name(self, name: str) -> Path:
        self._folder.mkdir(parents=True, exist_ok=True)
        candidate, number = self._folder / name, 1
        while candidate.exists():
            number += 1
            candidate = self._folder / f"{Path(name).stem}-{number}{Path(name).suffix}"
        return candidate
