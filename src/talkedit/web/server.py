import logging
import secrets
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from talkedit.app import ProjectAssembler, UserHome
from talkedit.drive import VideoSource
from talkedit.media import ToolPaths
from talkedit.plan import CutDescriber, TimeLabel
from talkedit.plan_changes import PlanChanges
from talkedit.progress import MonotonicClock
from talkedit.projects import ProjectRegistry
from talkedit.web.actions import (
    EditJobs,
    FolderOpener,
    OpenerFactory,
    PlanEditing,
    VideoUploads,
    WebServices,
)
from talkedit.web.api import (
    ActionEndpoint,
    CutEndpoint,
    FinderEndpoint,
    JobView,
    MarkEndpoint,
    MediaEndpoint,
    PlanEndpoint,
    ProjectEndpoint,
    RedoEndpoint,
    Route,
    Router,
    SettingsEndpoint,
    StartEndpoint,
    StateEndpoint,
    StaticEndpoint,
    UploadEndpoint,
    WebApplication,
)
from talkedit.web.http import AccessGuard, ResponseWriter, StaticFiles, WebRequest
from talkedit.web.jobs import JobLogHandler, JobTracker
from talkedit.web.views import (
    CostReader,
    PlanView,
    ProjectStatus,
    ProjectView,
    SettingsView,
    StageList,
)


class TalkeditRequestHandler(BaseHTTPRequestHandler):
    """stdlib handler; every request goes to the bound WebApplication."""

    application: ClassVar[WebApplication]
    server_version = "talkedit"

    def do_GET(self) -> None:
        self.answer()

    def do_POST(self) -> None:
        self.answer()

    def do_PUT(self) -> None:
        self.answer()

    def log_request(self, code: object = "-", size: object = "-") -> None:
        """The page asks for progress every second; one terminal line per request is noise."""

    def answer(self) -> None:
        address = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(address.query))
        request = WebRequest(self.command, address.path, query, self.headers, self.rfile)
        response = self.application.respond(request)
        try:
            response.write_to(ResponseWriter(self))
        except (BrokenPipeError, ConnectionResetError):
            return


class HandlerFactory:
    def bound(self, application: WebApplication) -> type[TalkeditRequestHandler]:
        return type("BoundHandler", (TalkeditRequestHandler,), {"application": application})


@dataclass(frozen=True)
class RunningServer:
    server: ThreadingHTTPServer
    address: str


@dataclass(frozen=True)
class ServerOptions:
    port: int
    folders: FolderOpener


class WebServerBuilder:
    """Composition root for `talkedit abrir`."""

    HOST: ClassVar[str] = "127.0.0.1"
    TOKEN_BYTES: ClassVar[int] = 24
    STATIC: ClassVar[Path] = Path(__file__).resolve().parent / "static"

    def __init__(self, home: UserHome, sources: VideoSource, logger: logging.Logger) -> None:
        self._home = home
        self._sources = sources
        self._logger = logger

    def build(self, options: ServerOptions) -> RunningServer:
        token = secrets.token_urlsafe(self.TOKEN_BYTES)
        server = ThreadingHTTPServer((self.HOST, options.port), TalkeditRequestHandler)
        port = server.server_address[1]
        guard = AccessGuard(token, frozenset({f"{self.HOST}:{port}", f"localhost:{port}"}))
        router = Router(self._routes(self._services(), options.folders))
        server.RequestHandlerClass = HandlerFactory().bound(WebApplication(guard, router))
        return RunningServer(server, f"http://{self.HOST}:{port}/?t={token}")

    def _services(self) -> WebServices:
        jobs = JobTracker.create(MonotonicClock())
        self._logger.addHandler(JobLogHandler(jobs))
        assembler = ProjectAssembler(ToolPaths.bundled(), self._home, self._logger)
        registry = ProjectRegistry.at(self._home.projects_file)
        return WebServices(
            assembler, registry, self._home.settings_store(), self._sources, jobs, self._logger
        )

    def _routes(self, services: WebServices, folders: FolderOpener) -> tuple[Route, ...]:
        openers = OpenerFactory(services)
        costs = CostReader()
        projects = ProjectView(ProjectStatus(), costs, StageList())
        static = StaticEndpoint(StaticFiles(self.STATIC))
        settings = SettingsEndpoint(services, SettingsView())
        state = StateEndpoint(services, projects, JobView(MonotonicClock()))
        general = (
            Route.of("GET", r"/", static),
            Route.of("GET", r"/static/[\w.-]+", static),
            Route.of("GET", r"/api/state", state),
            Route.of("GET", r"/api/settings", settings),
            Route.of("PUT", r"/api/settings", settings),
            Route.of("PUT", r"/api/videos", UploadEndpoint(VideoUploads(self._home.videos))),
            Route.of("POST", r"/api/projects", StartEndpoint(EditJobs(services, openers))),
        )
        parts = ProjectParts(services, openers, projects, costs, folders)
        return (*general, *ProjectRoutes().routes(parts))


@dataclass(frozen=True)
class ProjectParts:
    services: WebServices
    openers: OpenerFactory
    projects: ProjectView
    costs: CostReader
    folders: FolderOpener


class ProjectRoutes:
    PREFIX: ClassVar[str] = r"/api/projects/(?P<key>[0-9a-f]+)"

    def routes(self, parts: ProjectParts) -> tuple[Route, ...]:
        services, openers = parts.services, parts.openers
        jobs = EditJobs(services, openers)
        editing = PlanEditing(services, openers, PlanChanges())
        plan = PlanView(CutDescriber(TimeLabel()), parts.costs)
        table = (
            ("GET", "", ProjectEndpoint(services, parts.projects)),
            ("GET", "/plan", PlanEndpoint(services, openers, plan)),
            ("POST", "/(?P<action>continue|preview|approve)", ActionEndpoint(jobs)),
            ("POST", "/redo", RedoEndpoint(jobs)),
            ("POST", "/cuts", MarkEndpoint(editing)),
            ("POST", r"/cuts/(?P<cut>[\w-]+)/(?P<action>give-back|apply)", CutEndpoint(editing)),
            ("POST", "/finder", FinderEndpoint(services, parts.folders)),
            ("GET", "/media/(?P<which>player|preview|final)", MediaEndpoint(services)),
        )
        return tuple(Route.of(method, self.PREFIX + tail, endpoint) for method, tail, endpoint in table)
