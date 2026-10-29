import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any

from talkedit.errors import MediaError
from talkedit.media import CommandRunner, ToolPaths
from talkedit.settings import AudioIntensity, AudioSettings

SAMPLE_RATE = 48000
TRUE_PEAK_DB = -1.5
LOUDNESS_RANGE = 11
LOUDNORM_REPORT = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.DOTALL)


class CleaningChains:
    """ffmpeg filter chains per intensity. `{model}` is the RNNoise voice model path.
    ponytail: ffmpeg has no real de-reverb; RNNoise only softens room echo. Auphonic
    (paid) is the upgrade path when a room sounds too live.
    dynaudnorm, not speechnorm: speechnorm after arnndn hangs ffmpeg 9.0.2 at end of input."""

    CHAINS = MappingProxyType(
        {
            AudioIntensity.OFF: "anull",
            AudioIntensity.LIGHT: (
                "highpass=f=80,afftdn=nr=10:nf=-45,"
                "acompressor=threshold=-18dB:ratio=2:attack=15:release=250"
            ),
            AudioIntensity.NORMAL: (
                "highpass=f=80,arnndn=m='{model}':mix=0.8,afftdn=nr=8:nf=-50,"
                "dynaudnorm=f=250:g=15:p=0.9:m=8,"
                "acompressor=threshold=-20dB:ratio=3:attack=10:release=200"
            ),
            AudioIntensity.STRONG: (
                "highpass=f=90,arnndn=m='{model}',afftdn=nr=15:nf=-45,"
                "dynaudnorm=f=200:g=11:p=0.9:m=12,"
                "acompressor=threshold=-22dB:ratio=4:attack=5:release=150"
            ),
        }
    )

    def __init__(self, tools: ToolPaths) -> None:
        self._tools = tools

    def chain(self, intensity: AudioIntensity) -> str:
        return self.CHAINS[intensity].format(model=self._tools.rnnoise_model)


class LoudnessTarget:
    def __init__(self, settings: AudioSettings) -> None:
        self._settings = settings

    def measure_filter(self) -> str:
        return f"{self._base()}:print_format=json"

    def apply_filter(self, measured: dict[str, Any]) -> str:
        return (
            f"{self._base()}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true"
        )

    def _base(self) -> str:
        return f"loudnorm=I={self._settings.target_lufs}:TP={TRUE_PEAK_DB}:LRA={LOUDNESS_RANGE}"


class AudioCleaner:
    """Two passes: the first measures loudness after cleaning, the second applies the
    cleaning plus a linear gain to the target, so the voice is not pumped."""

    def __init__(self, runner: CommandRunner, tools: ToolPaths, chains: CleaningChains) -> None:
        self._runner = runner
        self._tools = tools
        self._chains = chains

    def clean(self, source: Path, target: Path, settings: AudioSettings) -> None:
        chain = self._chains.chain(settings.intensity)
        loudness = LoudnessTarget(settings)
        report = self._runner.capture(
            self._command(source, f"{chain},{loudness.measure_filter()}", ["-f", "null", "-"]),
            "audio-medicao",
        )
        final_filter = f"{chain},{loudness.apply_filter(self._parse(report))}"
        output = ["-c:a", "pcm_s16le", "-y", str(target)]
        self._runner.capture(self._command(source, final_filter, output), "audio-limpeza")

    def _command(self, source: Path, audio_filter: str, output: list[str]) -> list[str]:
        return [
            str(self._tools.ffmpeg),
            "-hide_banner",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-af",
            f"aresample={SAMPLE_RATE},{audio_filter},aresample={SAMPLE_RATE}",
            *output,
        ]

    def _parse(self, report: str) -> dict[str, Any]:
        found = LOUDNORM_REPORT.findall(report)
        if not found:
            raise MediaError(
                "Nao consegui medir o volume do audio.",
                "Confira se o video tem som. O log esta na pasta trabalho/logs.",
            )
        return json.loads(found[-1])
