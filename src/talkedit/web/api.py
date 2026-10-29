import re
from dataclasses import dataclass
from http import HTTPStatus
from types import MappingProxyType
from typing import Any, Callable, ClassVar, Protocol

from talkedit.errors import AccessError, BusyError, NotFoundError, ProjectError, TalkeditError
from talkedit.plan import TimeRange
from talkedit.progress import Clock
from talkedit.settings import Settings
from talkedit.web.actions import (
    EditJobs,
    FolderOpener,
    NewVideo,
    OpenerFactory,
    PlanEditing,
    VideoUploads,
    WebServices,
)
from talkedit.web.http import (
    AccessGuard,
    FileResponse,
    JsonResponse,
    Response,
    StaticFiles,
    WebRequest,
)
from talkedit.web.jobs import JobSnapshot
from talkedit.web.views import PlanView, ProjectView, SettingsView
from talkedit.workspace import RunMode


class Endpoint(Protocol):
    def respond(self, request: WebRequest, params: dict[str, str]) -> Response: ...


@dataclass(frozen=True)
class Route:
    method: str
    pattern: re.Pattern[str]
    endpoint: Endpoint

    @classmethod
    def of(cls, method: str, pattern: str, endpoint: Endpoint) -> "Route":
        return cls(method, re.compile(f"^{pattern}$"), endpoint)


class Router:
    def __init__(self, routes: tuple[Route, ...]) -> None:
        self._routes = routes

    def resolve(self, request: WebRequest) -> tuple[Endpoint, dict[str, str]]:
        for route in self._routes:
            found = route.pattern.match(request.path)
            if found and route.method == request.method:
                return route.endpoint, found.groupdict()
        raise NotFoundError("Esse endereco nao existe.", "Abra a pagina inicial do talkedit.")


class WebApplication:
    """Checks access, finds the endpoint, and turns any TalkeditError into a JSON error
    the page shows as-is (message plus what to do)."""

    STATUSES: ClassVar[tuple[tuple[type[TalkeditError], HTTPStatus], ...]] = (
        (AccessError, HTTPStatus.FORBIDDEN),
        (NotFoundError, HTTPStatus.NOT_FOUND),
        (BusyError, HTTPStatus.CONFLICT),
    )

    def __init__(self, guard: AccessGuard, router: Router) -> None:
        self._guard = guard
        self._router = router

    def respond(self, request: WebRequest) -> Response:
        try:
            self._guard.check(request)
            endpoint, params = self._router.resolve(request)
            return endpoint.respond(request, params)
        except TalkeditError as error:
            payload = {"error": error.message, "hint": error.hint}
            return JsonResponse(payload, self._status(error))

    def _status(self, error: TalkeditError) -> HTTPStatus:
        matches = [status for kind, status in self.STATUSES if isinstance(error, kind)]
        return matches[0] if matches else HTTPStatus.BAD_REQUEST


class JobView:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def view(self, job: JobSnapshot) -> dict[str, Any]:
        end = job.finished or self._clock.now()
        return {
            "kind": job.kind.value if job.kind else "",
            "key": job.project_key,
            "phase": job.phase.value,
            "stage": job.stage_label,
            "detail": job.detail,
            "elapsed": round(end - job.started) if job.started else 0,
            "error": job.error_message,
            "hint": job.error_hint,
        }


class StaticEndpoint:
    def __init__(self, files: StaticFiles) -> None:
        self._files = files

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        return self._files.response(request.path)


class StateEndpoint:
    def __init__(self, services: WebServices, projects: ProjectView, jobs: JobView) -> None:
        self._services = services
        self._projects = projects
        self._jobs = jobs

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        job = self._services.jobs.snapshot()
        rows = [
            self._projects.row(workspace, job) for workspace in self._services.registry.workspaces()
        ]
        settings = self._services.settings.current()
        defaults = {
            "style": settings.style,
            "pace": settings.pace.pace.value,
            "cleaning": settings.audio.intensity.value,
        }
        extra = {
            "rules": len(settings.editor.rules),
            "words": len(settings.transcription.hard_words),
        }
        return JsonResponse(
            {"job": self._jobs.view(job), "projects": rows, "defaults": {**defaults, **extra}}
        )


class SettingsEndpoint:
    def __init__(self, services: WebServices, view: SettingsView) -> None:
        self._services = services
        self._view = view

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        store = self._services.settings
        settings = store.save(request.json()) if request.method == "PUT" else store.current()
        payload = {"settings": self._view.view(settings), "factory": self._view.view(Settings())}
        return JsonResponse({**payload, "path": str(store.path)})


class UploadEndpoint:
    def __init__(self, uploads: VideoUploads) -> None:
        self._uploads = uploads

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        if request.length() <= 0:
            raise ProjectError("O video chegou vazio.", "Arraste o video de novo.")
        saved = self._uploads.save(request.param("name"), request.body, request.length())
        return JsonResponse({"path": str(saved), "name": saved.name})


class StartEndpoint:
    def __init__(self, jobs: EditJobs) -> None:
        self._jobs = jobs

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        body = request.json()
        source = str(body.get("source", "")).strip()
        if not source:
            raise ProjectError(
                "Escolha um video ou cole um link.", "Arraste o video ou cole o link do Drive."
            )
        mode = RunMode.TEST if body.get("test") is True else RunMode.REAL
        self._jobs.start_new(NewVideo(source, mode, str(body.get("style", ""))))
        return JsonResponse({"started": True}, HTTPStatus.ACCEPTED)


class ProjectEndpoint:
    def __init__(self, services: WebServices, projects: ProjectView) -> None:
        self._services = services
        self._projects = projects

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        workspace = self._services.registry.find(params["key"])
        return JsonResponse(self._projects.detail(workspace, self._services.jobs.snapshot()))


class PlanEndpoint:
    def __init__(self, services: WebServices, openers: OpenerFactory, view: PlanView) -> None:
        self._services = services
        self._openers = openers
        self._view = view

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        workspace = self._services.registry.find(params["key"])
        if not workspace.plan_file.exists():
            raise NotFoundError("O plano ainda nao existe.", "Espere a IA editora terminar.")
        return JsonResponse(self._view.plan(self._openers.for_read().open(workspace)))


class ActionEndpoint:
    """continue, preview and approve: each starts the background job."""

    def __init__(self, jobs: EditJobs) -> None:
        self._jobs = jobs

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        self._actions()[params["action"]](params["key"])
        return JsonResponse({"started": True}, HTTPStatus.ACCEPTED)

    def _actions(self) -> MappingProxyType[str, Callable[[str], None]]:
        jobs = self._jobs
        return MappingProxyType(
            {"continue": jobs.resume, "preview": jobs.preview, "approve": jobs.approve}
        )


class RedoEndpoint:
    MAX_REQUEST_CHARS: ClassVar[int] = 2000

    def __init__(self, jobs: EditJobs) -> None:
        self._jobs = jobs

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        text = str(request.json().get("request", "")).strip()[: self.MAX_REQUEST_CHARS]
        if not text:
            raise ProjectError(
                "Escreva o que a IA deve mudar.",
                "Ex.: esta cortando demais, seja mais conservador.",
            )
        self._jobs.redo(params["key"], text)
        return JsonResponse({"started": True}, HTTPStatus.ACCEPTED)


class CutEndpoint:
    def __init__(self, editing: PlanEditing) -> None:
        self._editing = editing

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        self._actions()[params["action"]](params["key"], params["cut"])
        return JsonResponse({"ok": True})

    def _actions(self) -> MappingProxyType[str, Callable[[str, str], None]]:
        return MappingProxyType({"give-back": self._editing.give_back, "apply": self._editing.apply})


class MarkEndpoint:
    def __init__(self, editing: PlanEditing) -> None:
        self._editing = editing

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        body = request.json()
        try:
            start, end = sorted((float(body["start"]), float(body["end"])))
        except (KeyError, TypeError, ValueError) as error:
            raise ProjectError(
                "Trecho marcado invalido.", "Arraste de novo na linha do tempo."
            ) from error
        self._editing.mark(params["key"], TimeRange(start=max(0.0, start), end=max(0.0, end)))
        return JsonResponse({"ok": True})


class FinderEndpoint:
    def __init__(self, services: WebServices, folders: FolderOpener) -> None:
        self._services = services
        self._folders = folders

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        workspace = self._services.registry.find(params["key"])
        folder = workspace.delivery_dir if workspace.delivery_dir.exists() else workspace.root
        self._folders.reveal(folder)
        return JsonResponse({"folder": str(folder)})


class MediaEndpoint:
    """The player copy, the preview and the final video, with Range so the page can seek."""

    def __init__(self, services: WebServices) -> None:
        self._services = services

    def respond(self, request: WebRequest, params: dict[str, str]) -> Response:
        workspace = self._services.registry.find(params["key"])
        files = {
            "player": workspace.player_video,
            "preview": workspace.preview_video,
            "final": workspace.youtube_video,
        }
        path = files[params["which"]]
        if not path.exists():
            raise NotFoundError("Esse video ainda nao existe.", "Espere a etapa terminar.")
        return FileResponse(path, "video/mp4", request.headers.get("Range", ""))
