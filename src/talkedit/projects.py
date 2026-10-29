import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from talkedit.app import ProjectAssembler, ProjectServices
from talkedit.errors import NotFoundError
from talkedit.pipeline import ProjectContext
from talkedit.progress import ProgressSink
from talkedit.workspace import ProjectState, ProjectStateStore, ProjectWorkspace


@dataclass(frozen=True)
class OpenProject:
    state: ProjectState
    context: ProjectContext
    services: ProjectServices


class ProjectOpener:
    """Accepts the video path or the project folder, so every command takes either."""

    def __init__(
        self, assembler: ProjectAssembler, progress: ProgressSink, registry: "ProjectRegistry"
    ) -> None:
        self._assembler = assembler
        self._progress = progress
        self._registry = registry

    def workspace(self, given: Path) -> ProjectWorkspace:
        if given.is_dir():
            return ProjectWorkspace(given)
        return ProjectWorkspace.beside(given)

    def open(self, workspace: ProjectWorkspace) -> OpenProject:
        return self.open_state(workspace, ProjectStateStore(workspace).load())

    def open_state(self, workspace: ProjectWorkspace, state: ProjectState) -> OpenProject:
        settings = self._assembler.settings(state.overrides)
        settings = settings.with_editor_request(state.editor_request)
        context = self._assembler.context(Path(state.source), workspace, settings)
        services = self._assembler.services(context, state.mode, self._progress)
        self._registry.remember(workspace.root)
        return OpenProject(state, context, services)


@dataclass(frozen=True)
class ProjectKey:
    """Short stable id for a project folder, used in page addresses."""

    LENGTH: ClassVar[int] = 12

    value: str

    @classmethod
    def of(cls, root: Path) -> "ProjectKey":
        digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
        return cls(digest[: cls.LENGTH])


class ProjectRegistry:
    """Remembers every project folder started from the terminal or the page, newest
    first, in ~/.talkedit/projetos.json. Folders that no longer exist are skipped."""

    LIMIT: ClassVar[int] = 50
    JSON_INDENT: ClassVar[int] = 2

    def __init__(self, path: Path, lock: threading.Lock) -> None:
        self._path = path
        self._lock = lock

    @classmethod
    def at(cls, path: Path) -> "ProjectRegistry":
        return cls(path, threading.Lock())

    def remember(self, root: Path) -> None:
        with self._lock:
            roots = [str(root.resolve())] + [
                item for item in self._read() if item != str(root.resolve())
            ]
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(roots[: self.LIMIT], indent=self.JSON_INDENT), encoding="utf-8")

    def workspaces(self) -> list[ProjectWorkspace]:
        with self._lock:
            roots = [Path(item) for item in self._read()]
        workspaces = [ProjectWorkspace(root) for root in roots]
        return [workspace for workspace in workspaces if workspace.state_file.exists()]

    def find(self, key: str) -> ProjectWorkspace:
        for workspace in self.workspaces():
            if ProjectKey.of(workspace.root).value == key:
                return workspace
        raise NotFoundError("Nao achei esse projeto.", "Volte para a lista de videos recentes.")

    def _read(self) -> list[str]:
        if not self._path.exists():
            return []
        return [str(item) for item in json.loads(self._path.read_text(encoding="utf-8"))]
