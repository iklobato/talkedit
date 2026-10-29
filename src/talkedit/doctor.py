import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from talkedit.app import ApiKeyReader
from talkedit.errors import TalkeditError
from talkedit.media import CommandRunner, ToolPaths
from talkedit.openrouter import API_BASE
from talkedit.settings import Settings

REQUIRED_FILTERS = ("arnndn", "loudnorm", "ass", "silencedetect")
CHECK_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    message: str


class InstallCheck(Protocol):
    def results(self) -> list[CheckResult]: ...


class ToolsCheck:
    def __init__(self, runner: CommandRunner, tools: ToolPaths) -> None:
        self._runner = runner
        self._tools = tools

    def results(self) -> list[CheckResult]:
        missing = [path for path in (self._tools.ffmpeg, self._tools.ffprobe) if not path.exists()]
        if missing:
            return [CheckResult(False, f"ffmpeg nao encontrado em {missing[0]}. Veja o GUIA.md.")]
        filters = self._runner.capture(
            [str(self._tools.ffmpeg), "-hide_banner", "-filters"], "verificar-filtros"
        )
        absent = [name for name in REQUIRED_FILTERS if f" {name} " not in filters]
        return [
            CheckResult(True, f"ffmpeg em {self._tools.ffmpeg}"),
            CheckResult(
                not absent,
                f"filtros do ffmpeg: {'faltando ' + ', '.join(absent) if absent else 'ok'}",
            ),
            CheckResult(
                self._tools.rnnoise_model.exists(),
                f"modelo de limpeza de voz em {self._tools.rnnoise_model}",
            ),
        ]


class OpenRouterCheck:
    def __init__(self, keys: ApiKeyReader, settings: Settings) -> None:
        self._keys = keys
        self._settings = settings

    def results(self) -> list[CheckResult]:
        try:
            key = self._keys.read()
            self._get(f"{API_BASE}/key", key)
        except TalkeditError as error:
            return [CheckResult(False, f"chave do OpenRouter: {error.message} {error.hint}")]
        except urllib.error.URLError as error:
            return [CheckResult(False, f"chave do OpenRouter recusada ou sem internet: {error}")]
        models = {model["id"] for model in self._get(f"{API_BASE}/models?output_modalities=all", key)["data"]}
        wanted = self._settings.models.model_dump(by_alias=True)
        return [CheckResult(True, "chave do OpenRouter aceita")] + [
            CheckResult(model in models, f"modelo de {role}: {model}")
            for role, model in wanted.items()
        ]

    def _get(self, url: str, key: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(request, timeout=CHECK_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))


class Doctor:
    def __init__(self, checks: list[InstallCheck], logger: logging.Logger) -> None:
        self._checks = checks
        self._logger = logger

    def report(self) -> bool:
        outcomes = [outcome for check in self._checks for outcome in check.results()]
        for outcome in outcomes:
            self._logger.info("  %s %s", "ok  " if outcome.passed else "ERRO", outcome.message)
        return all(outcome.passed for outcome in outcomes)
