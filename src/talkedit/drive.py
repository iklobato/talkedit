import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import Message
from functools import partial
from html.parser import HTMLParser
from http import HTTPStatus
from pathlib import Path
from typing import BinaryIO, ClassVar, Protocol

from talkedit.errors import ConfigError, DriveNotPublicError, MediaError


class DriveLinkParser:
    HOSTS: ClassVar[frozenset[str]] = frozenset(
        {"drive.google.com", "drive.usercontent.google.com", "docs.google.com"}
    )
    ID_PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"/file/d/([\w-]{10,})"),
        re.compile(r"[?&]id=([\w-]{10,})"),
    )
    FOLDER_MARKER: ClassVar[str] = "/folders/"
    DIRECT_DOWNLOAD: ClassVar[str] = (
        "https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    )

    def is_drive(self, text: str) -> bool:
        return (urllib.parse.urlparse(text).hostname or "") in self.HOSTS

    def file_id(self, url: str) -> str:
        if self.FOLDER_MARKER in url:
            raise ConfigError(
                "Esse link e de uma pasta do Google Drive, nao de um video.",
                "Abra a pasta, clique no video com o botao direito > Compartilhar > Copiar link.",
            )
        for pattern in self.ID_PATTERNS:
            found = pattern.search(url)
            if found:
                return found.group(1)
        raise ConfigError(
            f"Nao achei o arquivo no link {url}.",
            "Use o link de compartilhar do video, como https://drive.google.com/file/d/.../view",
        )

    def direct_url(self, file_id: str) -> str:
        """`confirm=t` skips the virus scan warning page that Drive shows for big files."""
        return self.DIRECT_DOWNLOAD.format(file_id=file_id)


class DownloadFormReader(HTMLParser):
    """Reads the "virus scan warning" page Drive shows for big files and builds the URL
    of its download button."""

    FORM_ID: ClassVar[str] = "download-form"

    def reset(self) -> None:
        super().reset()
        self._action = ""
        self._fields: dict[str, str] = {}
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "form":
            self._inside = values.get("id") == self.FORM_ID
            self._action = values.get("action", "") if self._inside else self._action
            return
        if self._inside and tag == "input" and values.get("type") == "hidden":
            self._fields[values.get("name", "")] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._inside = False

    def download_url(self, html: str) -> str:
        self.reset()
        self.feed(html)
        if not self._action:
            return ""
        return f"{self._action}?{urllib.parse.urlencode(self._fields)}"


@dataclass(frozen=True)
class HttpReply:
    PAGE_TYPE: ClassVar[str] = "text/html"
    SUCCESS: ClassVar[frozenset[HTTPStatus]] = frozenset(
        {HTTPStatus.OK, HTTPStatus.PARTIAL_CONTENT}
    )

    status: int
    content_type: str
    filename: str

    def is_success(self) -> bool:
        return self.status in self.SUCCESS

    def is_page(self) -> bool:
        return self.content_type == self.PAGE_TYPE


@dataclass(frozen=True)
class ByteCount:
    BYTES_PER_MB: ClassVar[int] = 1024 * 1024

    value: int

    def megabytes(self) -> int:
        return self.value // self.BYTES_PER_MB


class HttpFetcher(Protocol):
    def fetch(self, url: str, sink: Path) -> HttpReply: ...


class UrllibFetcher:
    """Streams the body to `sink` in 1 MB pieces, logging progress about ten times."""

    CHUNK_BYTES: ClassVar[int] = ByteCount.BYTES_PER_MB
    READ_TIMEOUT_SECONDS: ClassVar[int] = 60
    PROGRESS_STEPS: ClassVar[int] = 10
    USER_AGENT: ClassVar[str] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) talkedit"

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def fetch(self, url: str, sink: Path) -> HttpReply:
        request = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.READ_TIMEOUT_SECONDS) as response:
                self._copy(response, sink, int(response.headers.get("Content-Length") or 0))
                return self._reply(response.status, response.headers)
        except urllib.error.HTTPError as error:
            return HttpReply(status=error.code, content_type="", filename="")
        except (urllib.error.URLError, TimeoutError) as error:
            raise MediaError(
                f"A conexao com o Google Drive caiu: {error}.",
                "Confira a internet e rode o mesmo comando de novo.",
            ) from error

    def _copy(self, response: BinaryIO, sink: Path, total: int) -> None:
        copied = 0
        with sink.open("wb") as output:
            for chunk in iter(partial(response.read, self.CHUNK_BYTES), b""):
                output.write(chunk)
                copied += len(chunk)
                self._report(copied, len(chunk), total)

    def _report(self, copied: int, last_chunk: int, total: int) -> None:
        step = total // self.PROGRESS_STEPS
        if not step or copied // step == (copied - last_chunk) // step:
            return
        done, size = ByteCount(copied).megabytes(), ByteCount(total).megabytes()
        self._logger.info("    baixado %s de %s MB", done, size)

    def _reply(self, status: int, headers: Message) -> HttpReply:
        disposition = Message()
        disposition["content-disposition"] = headers.get("Content-Disposition", "")
        return HttpReply(
            status=status,
            content_type=headers.get_content_type(),
            filename=disposition.get_filename() or "",
        )


class DriveDownloader:
    """Downloads a public Google Drive file into `<folder>/<file id>/`. A second call
    with the same link reuses the file already there."""

    PARTIAL_SUFFIX: ClassVar[str] = ".parcial"

    def __init__(
        self, fetcher: HttpFetcher, parser: DriveLinkParser, logger: logging.Logger
    ) -> None:
        self._fetcher = fetcher
        self._parser = parser
        self._logger = logger

    def download(self, url: str, folder: Path) -> Path:
        file_id = self._parser.file_id(url)
        target_folder = folder / file_id
        existing = self._already_downloaded(target_folder)
        if existing:
            self._logger.info("Video ja baixado antes: %s", existing[0])
            return existing[0]
        target_folder.mkdir(parents=True, exist_ok=True)
        in_progress = target_folder / f"download{self.PARTIAL_SUFFIX}"
        self._logger.info("Baixando o video do Google Drive para %s", target_folder)
        reply = self._fetch_past_warning(self._parser.direct_url(file_id), in_progress)
        self._check(reply, in_progress)
        target = target_folder / (Path(reply.filename).name or f"drive-{file_id}.mp4")
        in_progress.replace(target)
        return target

    def _already_downloaded(self, target_folder: Path) -> list[Path]:
        files = [path for path in target_folder.glob("*") if path.is_file()]
        return [path for path in files if path.suffix != self.PARTIAL_SUFFIX]

    def _fetch_past_warning(self, url: str, in_progress: Path) -> HttpReply:
        reply = self._fetcher.fetch(url, in_progress)
        if not reply.is_page():
            return reply
        button = DownloadFormReader().download_url(
            in_progress.read_text(encoding="utf-8", errors="replace")
        )
        return self._fetcher.fetch(button, in_progress) if button else reply

    def _check(self, reply: HttpReply, in_progress: Path) -> None:
        """A refused download leaves no partial file behind."""
        if reply.is_success() and not reply.is_page():
            return
        in_progress.unlink(missing_ok=True)
        if not reply.is_success():
            raise DriveNotPublicError.saying(
                f"O Google Drive respondeu erro {reply.status}: "
                "o arquivo nao existe ou nao esta publico."
            )
        raise DriveNotPublicError.saying(
            "O Google Drive mostrou uma pagina em vez do video: o arquivo nao esta publico "
            "ou passou do limite de downloads do dia."
        )


class VideoSource:
    """The `editar` argument: a local path, or a Google Drive link that is downloaded first."""

    WEB_PREFIXES: ClassVar[tuple[str, ...]] = ("http://", "https://")

    def __init__(
        self, parser: DriveLinkParser, downloader: DriveDownloader, default_folder: Path
    ) -> None:
        self._parser = parser
        self._downloader = downloader
        self._default_folder = default_folder

    def local_path(self, given: str, chosen_folder: Path | None) -> Path:
        """`chosen_folder` is None when the user did not pass --pasta."""
        if self._parser.is_drive(given):
            folder = chosen_folder or self._default_folder
            return self._downloader.download(given, folder).resolve()
        if given.startswith(self.WEB_PREFIXES):
            raise ConfigError(
                f"So sei baixar video do Google Drive, e o link e de outro site: {given}",
                "Baixe o video para o Mac e passe o caminho do arquivo.",
            )
        return Path(given).expanduser().resolve()
