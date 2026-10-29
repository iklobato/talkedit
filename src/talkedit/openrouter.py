import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from talkedit.errors import AIResponseError, OpenRouterError

API_BASE = "https://openrouter.ai/api/v1"
HTTP_TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 2
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
HTTP_UNAUTHORIZED = 401
HTTP_PAYMENT_REQUIRED = 402
ERROR_BODY_CHARS = 500
JSON_INDENT = 2


class HttpTransport(Protocol):
    def post_json(self, url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]: ...


class UrllibTransport:
    """POST with retries on rate limits and server errors (3 tries, 2 s then 4 s)."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def post_json(self, url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._post_once(url, payload, api_key)
            except urllib.error.HTTPError as error:
                self._raise_unless_retryable(error, attempt)
            except (urllib.error.URLError, TimeoutError) as error:
                self._raise_if_last(error, attempt)
            self._logger.info("OpenRouter falhou, tentando de novo (%s/%s)", attempt, MAX_ATTEMPTS)
            time.sleep(RETRY_BASE_SECONDS**attempt)
        raise OpenRouterError("O OpenRouter nao respondeu.", "Tente de novo em alguns minutos.")

    def _post_once(self, url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    def _raise_unless_retryable(self, error: urllib.error.HTTPError, attempt: int) -> None:
        body = error.read().decode("utf-8", errors="replace")[:ERROR_BODY_CHARS]
        if error.code == HTTP_UNAUTHORIZED:
            raise OpenRouterError(
                "O OpenRouter recusou a chave.",
                "Confira a chave com: talkedit verificar",
            ) from error
        if error.code == HTTP_PAYMENT_REQUIRED:
            raise OpenRouterError(
                "Acabou o credito no OpenRouter.",
                "Coloque credito em https://openrouter.ai/settings/credits e rode talkedit continuar.",
            ) from error
        if error.code not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
            raise OpenRouterError(
                f"O OpenRouter respondeu erro {error.code}: {body}",
                "Se o erro fala do modelo, troque o modelo no config.toml.",
            ) from error

    def _raise_if_last(self, error: OSError, attempt: int) -> None:
        if attempt == MAX_ATTEMPTS:
            raise OpenRouterError(
                f"Sem conexao com o OpenRouter: {error}.",
                "Confira a internet e rode talkedit continuar.",
            ) from error


@dataclass(frozen=True)
class ChatRequest:
    model: str
    system: str
    user_parts: list[dict[str, Any]]
    schema_name: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class ChatReply:
    content: dict[str, Any]
    cost: float


class OpenRouterClient:
    def __init__(self, api_key: str, transport: HttpTransport) -> None:
        self._api_key = api_key
        self._transport = transport

    def chat(self, request: ChatRequest) -> ChatReply:
        response = self._transport.post_json(
            f"{API_BASE}/chat/completions", self._chat_payload(request), self._api_key
        )
        return ChatReply(content=self._json_content(response), cost=self._cost(response))

    def transcribe(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._transport.post_json(f"{API_BASE}/audio/transcriptions", payload, self._api_key)

    def _chat_payload(self, request: ChatRequest) -> dict[str, Any]:
        return {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user_parts},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "strict": True,
                    "schema": request.schema,
                },
            },
        }

    def _json_content(self, response: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise AIResponseError(
                f"A IA respondeu num formato que nao entendi: {str(response)[:ERROR_BODY_CHARS]}",
                "Rode talkedit continuar para tentar de novo.",
            ) from error

    def _cost(self, response: dict[str, Any]) -> float:
        return float(response.get("usage", {}).get("cost", 0.0))


class CostFunction(Enum):
    TRANSCRIPTION = "transcricao"
    EDITOR = "editora"
    REVIEWER = "revisora"


class CostLedger:
    """Real USD spent per AI function, as reported by OpenRouter. Saved after each charge
    because a run can stop half way and continue in another terminal."""

    def __init__(self, path: Path, spent: dict[str, float], lock: threading.Lock) -> None:
        self._path = path
        self._spent = spent
        self._lock = lock

    @classmethod
    def load(cls, path: Path) -> "CostLedger":
        spent = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return cls(path, spent, threading.Lock())

    def charge(self, function: CostFunction, usd: float) -> None:
        with self._lock:
            self._spent[function.value] = self._spent.get(function.value, 0.0) + usd
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._spent, indent=JSON_INDENT), encoding="utf-8")

    def by_function(self) -> dict[str, float]:
        return dict(self._spent)

    def total(self) -> float:
        return sum(self._spent.values())
