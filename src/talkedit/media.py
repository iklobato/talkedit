import json
import logging
import os
import shlex
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from talkedit.errors import MediaError

LOG_TAIL_CHARS = 1500
REPO_ROOT_DEPTH = 2
MAX_FPS_DENOMINATOR = 1001
QUARTER_TURN_DEGREES = 90
HALF_TURN_DEGREES = 180


@dataclass(frozen=True)
class ToolPaths:
    ffmpeg: Path
    ffprobe: Path
    rnnoise_model: Path

    @classmethod
    def bundled(cls) -> "ToolPaths":
        tools = Path(__file__).resolve().parents[REPO_ROOT_DEPTH] / "tools"
        return cls(tools / "ffmpeg", tools / "ffprobe", tools / "sh.rnnn")


class CommandRunner:
    """Runs a shell command with os.system and keeps its output in a log file.
    One log per label, so parallel calls must use distinct labels."""

    def __init__(self, log_dir: Path, logger: logging.Logger) -> None:
        self._log_dir = log_dir
        self._logger = logger

    def capture(self, args: list[str], label: str) -> str:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._log_dir / f"{label}.log"
        self._logger.debug("comando: %s", shlex.join(args))
        status = os.system(f"{shlex.join(args)} < /dev/null > {shlex.quote(str(log_path))} 2>&1")
        output = log_path.read_text(encoding="utf-8", errors="replace")
        if os.waitstatus_to_exitcode(status) != 0:
            raise MediaError(
                f"O comando '{label}' falhou. Final da saida: {output[-LOG_TAIL_CHARS:]}",
                f"O log completo esta em {log_path}.",
            )
        return output


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    fps: Fraction
    width: int
    height: int
    has_audio: bool


class MediaProbe:
    def __init__(self, runner: CommandRunner, tools: ToolPaths) -> None:
        self._runner = runner
        self._tools = tools

    def probe(self, path: Path) -> MediaInfo:
        if not path.exists():
            raise MediaError(
                f"O arquivo {path} nao existe.", "Confira o caminho do video."
            )
        output = self._runner.capture(self._command(path), f"ffprobe-{path.stem}")
        report = self._parse(output, path)
        video = self._video_stream(report, path)
        width, height = self._display_size(video)
        return MediaInfo(
            duration=float(report["format"]["duration"]),
            fps=Fraction(video["avg_frame_rate"]).limit_denominator(
                MAX_FPS_DENOMINATOR
            ),
            width=width,
            height=height,
            has_audio=any(stream["codec_type"] == "audio" for stream in report["streams"]),
        )

    def _command(self, path: Path) -> list[str]:
        return [
            str(self._tools.ffprobe),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]

    def _parse(self, output: str, path: Path) -> dict[str, Any]:
        try:
            return json.loads(output)
        except json.JSONDecodeError as error:
            raise MediaError(
                f"Nao consegui ler as informacoes de {path}.",
                "O arquivo pode estar corrompido. Tente abrir no QuickTime.",
            ) from error

    def _video_stream(self, report: dict[str, Any], path: Path) -> dict[str, Any]:
        for stream in report.get("streams", []):
            if stream["codec_type"] == "video":
                return stream
        raise MediaError(f"{path} nao tem imagem de video.", "Use um arquivo de video.")

    def _display_size(self, video: dict[str, Any]) -> tuple[int, int]:
        rotation = 0
        for side_data in video.get("side_data_list", []):
            rotation = int(side_data.get("rotation", rotation))
        if abs(rotation) % HALF_TURN_DEGREES == QUARTER_TURN_DEGREES:
            return int(video["height"]), int(video["width"])
        return int(video["width"]), int(video["height"])
