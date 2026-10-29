import io
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from typing import Any, Iterator

import pytest
from test_end_to_end import SampleVideo

from talkedit.app import UserHome
from talkedit.drive import DriveDownloader, DriveLinkParser, UrllibFetcher, VideoSource
from talkedit.errors import AccessError, BusyError, MediaError, ProjectError
from talkedit.progress import MonotonicClock
from talkedit.web.actions import VideoUploads
from talkedit.web.http import AccessGuard, ByteRange, WebRequest
from talkedit.web.jobs import JobKind, JobPhase, JobRequest, JobTracker
from talkedit.web.server import RunningServer, ServerOptions, WebServerBuilder


class TestByteRange:
    SIZE = 1000
    LAST = 999
    TAIL = 100
    MIDDLE = 500

    def test_open_ended_range_runs_to_the_end(self) -> None:
        span = ByteRange.parse(f"bytes={self.MIDDLE}-", self.SIZE)

        assert span == ByteRange(self.MIDDLE, self.LAST)

    def test_suffix_range_takes_the_last_bytes(self) -> None:
        span = ByteRange.parse(f"bytes=-{self.TAIL}", self.SIZE)

        assert span is not None and span.length() == self.TAIL

    def test_end_past_the_file_is_clamped(self) -> None:
        assert ByteRange.parse("bytes=0-5000", self.SIZE) == ByteRange(0, self.LAST)

    @pytest.mark.parametrize("header", ["", "bytes=", "bytes=900-100", "items=0-10"])
    def test_missing_or_broken_range_means_the_whole_file(self, header: str) -> None:
        assert ByteRange.parse(header, self.SIZE) is None


class RequestFactory:
    def request(self, path: str, headers: dict[str, str]) -> WebRequest:
        message = Message()
        for name, value in headers.items():
            message[name] = value
        query = {"t": headers.pop("query-token")} if "query-token" in headers else {}
        return WebRequest("GET", path, query, message, io.BytesIO(b""))


class TestAccessGuard:
    TOKEN = "segredo-de-teste"
    HOST = "127.0.0.1:8000"

    def guard(self) -> AccessGuard:
        return AccessGuard(self.TOKEN, frozenset({self.HOST}))

    def test_api_call_with_the_token_passes(self) -> None:
        request = RequestFactory().request(
            "/api/state", {"Host": self.HOST, "X-Talkedit-Token": self.TOKEN}
        )

        self.guard().check(request)

    def test_api_call_without_token_is_refused(self) -> None:
        request = RequestFactory().request("/api/state", {"Host": self.HOST})

        with pytest.raises(AccessError) as raised:
            self.guard().check(request)

        assert raised.value.message == "Acesso negado."

    def test_other_host_is_refused_even_with_the_token(self) -> None:
        request = RequestFactory().request(
            "/api/state", {"Host": "evil.example:8000", "X-Talkedit-Token": self.TOKEN}
        )

        with pytest.raises(AccessError) as raised:
            self.guard().check(request)

        assert raised.value.message == "Endereco nao permitido."

    def test_page_files_need_no_token(self) -> None:
        self.guard().check(RequestFactory().request("/static/app.js", {"Host": self.HOST}))


class TestVideoUploads:
    BODY = b"\x00\x00\x00\x18ftypmp42 video"
    PROMISED_LENGTH = 1000

    def test_name_is_cleaned_and_a_used_name_gets_a_number(self, tmp_path: Path) -> None:
        uploads = VideoUploads(tmp_path)

        first = uploads.save("../../minha aula?.mp4", io.BytesIO(self.BODY), len(self.BODY))
        second = uploads.save("minha aula_.mp4", io.BytesIO(self.BODY), len(self.BODY))

        assert (first.name, second.name) == ("minha aula_.mp4", "minha aula_-2.mp4")
        assert first.parent == tmp_path and first.read_bytes() == self.BODY

    def test_file_that_is_not_a_video_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError) as raised:
            VideoUploads(tmp_path).save("senhas.txt", io.BytesIO(self.BODY), len(self.BODY))

        assert raised.value.hint == "Use um arquivo .mp4, .mov, .m4v, .mkv, .webm ou .avi."
        assert list(tmp_path.iterdir()) == []

    def test_cut_short_upload_leaves_nothing(self, tmp_path: Path) -> None:
        with pytest.raises(MediaError) as raised:
            VideoUploads(tmp_path).save("aula.mp4", io.BytesIO(self.BODY), self.PROMISED_LENGTH)

        assert raised.value.message == "O envio do video foi interrompido."

        assert list(tmp_path.iterdir()) == []


class TrackerWaiter:
    TIMEOUT_SECONDS = 5.0
    STEP_SECONDS = 0.02
    SETTLE_SECONDS = 0.3

    def finished(self, tracker: JobTracker) -> JobPhase:
        deadline = time.monotonic() + self.TIMEOUT_SECONDS
        while tracker.snapshot().is_running() and time.monotonic() < deadline:
            time.sleep(self.STEP_SECONDS)
        return tracker.snapshot().phase


class TestJobTracker:
    def test_second_job_is_refused_while_one_runs(self) -> None:
        tracker, release = JobTracker.create(MonotonicClock()), threading.Event()
        tracker.start(JobRequest(JobKind.EDIT, "a", release.wait))

        with pytest.raises(BusyError):
            tracker.start(JobRequest(JobKind.PREVIEW, "b", lambda: None))

        release.set()
        assert TrackerWaiter().finished(tracker) is JobPhase.DONE

    def test_talkedit_error_shows_message_and_hint(self) -> None:
        tracker = JobTracker.create(MonotonicClock())

        def fail() -> None:
            raise ProjectError("Deu ruim.", "Faca outra coisa.")

        tracker.start(JobRequest(JobKind.EDIT, "a", fail))

        assert TrackerWaiter().finished(tracker) is JobPhase.FAILED
        assert (tracker.snapshot().error_message, tracker.snapshot().error_hint) == (
            "Deu ruim.",
            "Faca outra coisa.",
        )

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_unexpected_crash_still_ends_as_failed(self) -> None:
        tracker = JobTracker.create(MonotonicClock())

        def crash() -> None:
            raise KeyError("bug")

        tracker.start(JobRequest(JobKind.EDIT, "a", crash))
        phase = TrackerWaiter().finished(tracker)
        time.sleep(TrackerWaiter.SETTLE_SECONDS)

        assert phase is JobPhase.FAILED
        assert tracker.snapshot().error_message == JobTracker.CRASH_MESSAGE


class RecordingFolders:
    def __init__(self, opened: list[Path]) -> None:
        self._opened = opened

    def reveal(self, folder: Path) -> None:
        self._opened.append(folder)


class LiveServer:
    """The real HTTP server on a free port, driven like the page drives it."""

    POLL_SECONDS = 0.3
    TIMEOUT_SECONDS = 120.0

    def __init__(self, base: str, token: str) -> None:
        self._base = base
        self._token = token

    @classmethod
    def at(cls, address: str) -> "LiveServer":
        base, _, token = address.partition("/?t=")
        return cls(base, token)

    @property
    def base(self) -> str:
        return self._base

    def call(self, method: str, path: str, body: bytes | None = None) -> Any:
        request = urllib.request.Request(self._base + path, data=body, method=method)
        request.add_header("X-Talkedit-Token", self._token)
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.call("POST", path, json.dumps(payload).encode("utf-8"))

    def raw(self, path: str, headers: dict[str, str]) -> tuple[int, bytes]:
        request = urllib.request.Request(self._base + path + f"?t={self._token}", headers=headers)
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()

    def wait_job(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.TIMEOUT_SECONDS
        job = self.call("GET", "/api/state")["job"]
        while job["phase"] == "rodando" and time.monotonic() < deadline:
            time.sleep(self.POLL_SECONDS)
            job = self.call("GET", "/api/state")["job"]
        return job


class ServerSetup:
    def start(self, home: UserHome, opened: list[Path]) -> RunningServer:
        logger = logging.getLogger("talkedit-web-teste")
        parser = DriveLinkParser()
        sources = VideoSource(parser, DriveDownloader(UrllibFetcher(logger), parser, logger), home.videos)
        running = WebServerBuilder(home, sources, logger).build(ServerOptions(0, RecordingFolders(opened)))
        threading.Thread(target=running.server.serve_forever, daemon=True).start()
        return running


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[tuple[LiveServer, UserHome, list[Path]]]:
    home, opened = UserHome(tmp_path / "home", tmp_path / "videos"), []
    running = ServerSetup().start(home, opened)
    yield LiveServer.at(running.address), home, opened
    running.server.shutdown()
    running.server.server_close()


class ReviewFlow:
    """Upload, plan in test mode, give one cut back, approve, then read the results."""

    RANGE_BYTES = 100

    def observe(self, live: LiveServer, sample: Path) -> dict[str, Any]:
        uploaded = live.call("PUT", "/api/videos?name=aula.mp4", sample.read_bytes())
        live.post("/api/projects", {"source": uploaded["path"], "test": True})
        planned = live.wait_job()
        key = planned["key"]
        plan = live.call("GET", f"/api/projects/{key}/plan")
        live.post(f"/api/projects/{key}/cuts/{plan['cuts'][0]['id']}/give-back", {})
        restored = live.call("GET", f"/api/projects/{key}/plan")
        live.post(f"/api/projects/{key}/approve", {})
        approved = live.wait_job()
        ranged = live.raw(f"/api/projects/{key}/media/final", {"Range": f"bytes=0-{self.RANGE_BYTES - 1}"})
        live.post(f"/api/projects/{key}/finder", {})
        detail = live.call("GET", f"/api/projects/{key}")
        return {"phases": (planned["phase"], approved["phase"]), "plan": plan, "restored": restored, "detail": detail, "ranged": ranged}


class TestWebEndToEnd:
    def test_drop_plan_review_and_approve_through_the_page_api(
        self, tmp_path: Path, live_server: tuple[LiveServer, UserHome, list[Path]]
    ) -> None:
        live, home, opened = live_server
        sample = tmp_path / "bruto.mp4"
        SampleVideo().make(sample)

        seen = ReviewFlow().observe(live, sample)

        assert seen["phases"] == ("pronto", "pronto"), seen["phases"]
        assert seen["restored"]["cuts"][0]["status"] == "devolvido"
        assert seen["restored"]["removedCount"] == seen["plan"]["removedCount"] - 1
        assert (seen["detail"]["status"], seen["detail"]["hasVideo"]) == ("ready", True)
        status, body = seen["ranged"]
        assert (status, len(body)) == (HTTPStatus.PARTIAL_CONTENT, ReviewFlow.RANGE_BYTES)
        assert opened == [home.videos.resolve() / "aula_talkedit" / "entrega"]

    def test_api_without_token_is_refused(self, live_server: tuple[LiveServer, UserHome, list[Path]]) -> None:
        live, _, _ = live_server

        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(live.base + "/api/state")

        assert raised.value.code == HTTPStatus.FORBIDDEN
