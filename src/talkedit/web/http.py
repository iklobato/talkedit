import hmac
import json
import re
from dataclasses import dataclass
from email.message import Message
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Protocol

from talkedit.errors import AccessError, NotFoundError, ProjectError


class Readable(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


@dataclass(frozen=True)
class WebRequest:
    MAX_JSON_BYTES: ClassVar[int] = 1024 * 1024

    method: str
    path: str
    query: dict[str, str]
    headers: Message
    body: Readable

    def length(self) -> int:
        return int(self.headers.get("Content-Length") or 0)

    def json(self) -> dict[str, Any]:
        if self.length() > self.MAX_JSON_BYTES:
            raise ProjectError("O pedido e grande demais.", "Recarregue a pagina.")
        raw = self.body.read(self.length()) if self.length() else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProjectError(
                "A pagina mandou um pedido que nao entendi.", "Recarregue a pagina."
            ) from error
        if not isinstance(parsed, dict):
            raise ProjectError("A pagina mandou um pedido que nao entendi.", "Recarregue a pagina.")
        return parsed

    def param(self, name: str) -> str:
        if name not in self.query:
            raise ProjectError(f"Faltou '{name}' no pedido.", "Recarregue a pagina.")
        return self.query[name]


class ResponseWriter:
    """Thin wrapper over the stdlib handler so responses never touch it directly."""

    SECURITY_HEADERS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("X-Content-Type-Options", "nosniff"),
        ("Cache-Control", "no-store"),
        ("Referrer-Policy", "no-referrer"),
    )

    def __init__(self, handler: BaseHTTPRequestHandler) -> None:
        self._handler = handler

    def head(self, status: int, headers: list[tuple[str, str]]) -> None:
        self._handler.send_response(status)
        for name, value in [*self.SECURITY_HEADERS, *headers]:
            self._handler.send_header(name, value)
        self._handler.end_headers()

    def body(self, chunk: bytes) -> None:
        self._handler.wfile.write(chunk)


class Response(Protocol):
    def write_to(self, writer: ResponseWriter) -> None: ...


@dataclass(frozen=True)
class JsonResponse:
    payload: Any
    status: HTTPStatus = HTTPStatus.OK

    def write_to(self, writer: ResponseWriter) -> None:
        body = json.dumps(self.payload, ensure_ascii=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ]
        writer.head(self.status, headers)
        writer.body(body)


@dataclass(frozen=True)
class StaticResponse:
    PAGE_POLICY: ClassVar[str] = (
        "default-src 'self'; media-src 'self' blob:; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"
    )

    body: bytes
    content_type: str

    def write_to(self, writer: ResponseWriter) -> None:
        headers = [
            ("Content-Type", self.content_type),
            ("Content-Length", str(len(self.body))),
            ("Content-Security-Policy", self.PAGE_POLICY),
        ]
        writer.head(HTTPStatus.OK, headers)
        writer.body(self.body)


@dataclass(frozen=True)
class ByteRange:
    """One `Range: bytes=a-b` span, the only form a <video> element asks for."""

    PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"bytes=(\d*)-(\d*)$")

    first: int
    last: int

    @classmethod
    def parse(cls, header: str, size: int) -> "ByteRange | None":
        """None means "send the whole file"; a malformed or empty range is ignored."""
        found = cls.PATTERN.match(header.strip())
        if not found or size == 0 or not any(found.groups()):
            return None
        start_text, end_text = found.groups()
        if not start_text:
            return cls(max(0, size - int(end_text)), size - 1)
        last = min(int(end_text), size - 1) if end_text else size - 1
        first = int(start_text)
        return cls(first, last) if first <= last else None

    def length(self) -> int:
        return self.last - self.first + 1


@dataclass(frozen=True)
class FileResponse:
    CHUNK_BYTES: ClassVar[int] = 1024 * 1024

    path: Path
    content_type: str
    range_header: str

    def write_to(self, writer: ResponseWriter) -> None:
        size = self.path.stat().st_size
        span = ByteRange.parse(self.range_header, size)
        whole = ByteRange(0, size - 1) if size else ByteRange(0, -1)
        headers = [("Content-Type", self.content_type), ("Accept-Ranges", "bytes")]
        if span:
            headers.append(("Content-Range", f"bytes {span.first}-{span.last}/{size}"))
        chosen = span or whole
        writer.head(
            HTTPStatus.PARTIAL_CONTENT if span else HTTPStatus.OK,
            [*headers, ("Content-Length", str(chosen.length()))],
        )
        self._stream(writer, chosen)

    def _stream(self, writer: ResponseWriter, span: ByteRange) -> None:
        with self.path.open("rb") as source:
            source.seek(span.first)
            for size in self._chunk_sizes(span.length()):
                writer.body(source.read(size))

    def _chunk_sizes(self, total: int) -> list[int]:
        full, rest = divmod(max(0, total), self.CHUNK_BYTES)
        return [self.CHUNK_BYTES] * full + ([rest] if rest else [])


class StaticFiles:
    """Serves only the files that ship in web/static; nothing else on disk is reachable."""

    TYPES: ClassVar[MappingProxyType[str, str]] = MappingProxyType(
        {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }
    )

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def response(self, path: str) -> StaticResponse:
        name = "index.html" if path in ("/", "/index.html") else path.removeprefix("/static/")
        shipped = {item.name: item for item in self._folder.iterdir() if item.is_file()}
        if name not in shipped:
            raise NotFoundError("Essa pagina nao existe.", "Abra o endereco inicial do talkedit.")
        file = shipped[name]
        return StaticResponse(
            file.read_bytes(), self.TYPES.get(file.suffix, "application/octet-stream")
        )


class AccessGuard:
    """The server listens on 127.0.0.1 only. On top of that, every API call must carry
    the secret token from the address `talkedit abrir` opened, and the Host header must
    be this server, so a web site cannot drive it through the browser."""

    TOKEN_HEADER: ClassVar[str] = "X-Talkedit-Token"
    TOKEN_QUERY: ClassVar[str] = "t"

    def __init__(self, token: str, hosts: frozenset[str]) -> None:
        self._token = token
        self._hosts = hosts

    def check(self, request: WebRequest) -> None:
        if request.headers.get("Host", "") not in self._hosts:
            raise AccessError(
                "Endereco nao permitido.", "Abra o talkedit pelo endereco que o comando mostrou."
            )
        if not request.path.startswith("/api/"):
            return
        given = request.headers.get(self.TOKEN_HEADER) or request.query.get(self.TOKEN_QUERY, "")
        if not hmac.compare_digest(given.encode("utf-8"), self._token.encode("utf-8")):
            raise AccessError("Acesso negado.", "Feche esta aba e rode talkedit abrir de novo.")
