import base64
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from talkedit.errors import AIResponseError
from talkedit.media import CommandRunner, ToolPaths
from talkedit.openrouter import CostFunction, CostLedger, OpenRouterClient
from talkedit.plan import TimeRange
from talkedit.settings import Settings
from talkedit.transcript import TokenKind, Transcript, Word

SILENCE_LINE = re.compile(r"silence_(start|end): (-?[\d.]+)")
SILENCE_THRESHOLD = "-35dB"
SILENCE_MIN_SECONDS = 0.3
CHUNK_SECONDS = 120.0
CHUNK_SEARCH_SECONDS = 20.0
CHUNK_BITRATE = "64k"
MAX_PARALLEL_CHUNKS = 4
FAKE_WORD_STEP = 0.35
FAKE_WORD_LENGTH = 0.3
EDGES_PER_RANGE = 2


class SilenceDetector:
    def __init__(self, runner: CommandRunner, tools: ToolPaths) -> None:
        self._runner = runner
        self._tools = tools

    def silences(self, audio: Path, duration: float) -> list[TimeRange]:
        output = self._runner.capture(
            [
                str(self._tools.ffmpeg),
                "-hide_banner",
                "-nostats",
                "-i",
                str(audio),
                "-af",
                f"silencedetect=n={SILENCE_THRESHOLD}:d={SILENCE_MIN_SECONDS}",
                "-f",
                "null",
                "-",
            ],
            "silencio",
        )
        return self._pair([float(value) for _, value in SILENCE_LINE.findall(output)], duration)

    def _pair(self, edges: list[float], duration: float) -> list[TimeRange]:
        if len(edges) % EDGES_PER_RANGE:
            edges = [*edges, duration]
        starts, ends = edges[0::EDGES_PER_RANGE], edges[1::EDGES_PER_RANGE]
        return [
            TimeRange(start=max(0.0, start), end=end)
            for start, end in zip(starts, ends, strict=True)
        ]


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    offset: float
    duration: float


class ChunkBoundaries:
    """Every ~2 min, moved to the middle of the nearest silence so no word is split."""

    def boundaries(self, silences: list[TimeRange], duration: float) -> list[float]:
        points = [0.0]
        target = CHUNK_SECONDS
        while target < duration - CHUNK_SEARCH_SECONDS:
            points.append(self._nearest_silence(silences, target))
            target = points[-1] + CHUNK_SECONDS
        return [*points, duration]

    def _nearest_silence(self, silences: list[TimeRange], target: float) -> float:
        middles = [span.middle() for span in silences]
        near = [middle for middle in middles if abs(middle - target) <= CHUNK_SEARCH_SECONDS]
        return min(near, key=lambda middle: abs(middle - target), default=target)


class AudioChunker:
    def __init__(self, runner: CommandRunner, tools: ToolPaths, detector: SilenceDetector) -> None:
        self._runner = runner
        self._tools = tools
        self._detector = detector

    def split(self, audio: Path, duration: float, folder: Path) -> list[AudioChunk]:
        folder.mkdir(parents=True, exist_ok=True)
        points = ChunkBoundaries().boundaries(self._detector.silences(audio, duration), duration)
        return [
            self._encode(audio, folder / f"pedaco{index:03d}.mp3", (start, end))
            for index, (start, end) in enumerate(zip(points, points[1:]))
        ]

    def _encode(self, audio: Path, target: Path, span: tuple[float, float]) -> AudioChunk:
        start, end = span
        self._runner.capture(
            [str(self._tools.ffmpeg), "-hide_banner", "-ss", f"{start:.3f}", "-to", f"{end:.3f}"]
            + ["-i", str(audio), "-ac", "1", "-b:a", CHUNK_BITRATE, "-y", str(target)],
            target.stem,
        )
        return AudioChunk(path=target, offset=start, duration=end - start)


class Transcriber(Protocol):
    def transcribe(self, audio: Path, duration: float) -> Transcript: ...


class TranscriptionParser:
    def words(self, response: dict[str, Any], offset: float) -> list[Word]:
        if "words" not in response:
            raise AIResponseError(
                "A transcricao voltou sem o tempo de cada palavra.",
                "Use um modelo com tempo por palavra, como elevenlabs/scribe-v2.",
            )
        return [self._word(entry, offset) for entry in response["words"] if entry["word"].strip()]

    def _word(self, entry: dict[str, Any], offset: float) -> Word:
        kind = TokenKind(entry.get("type", TokenKind.WORD.value))
        return Word(
            text=entry["word"].strip(),
            start=float(entry["start"]) + offset,
            end=float(entry["end"]) + offset,
            kind=kind,
        )


@dataclass(frozen=True)
class TranscriptionContext:
    settings: Settings
    ledger: CostLedger
    chunk_folder: Path


class OpenRouterTranscriber:
    def __init__(
        self, client: OpenRouterClient, chunker: AudioChunker, context: TranscriptionContext
    ) -> None:
        self._client = client
        self._chunker = chunker
        self._context = context

    def transcribe(self, audio: Path, duration: float) -> Transcript:
        chunks = self._chunker.split(audio, duration, self._context.chunk_folder)
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CHUNKS) as pool:
            parts = list(pool.map(self._transcribe_chunk, chunks))
        words = sorted((word for part in parts for word in part), key=lambda word: word.start)
        language = self._context.settings.transcription.language
        return Transcript(language=language, duration=duration, words=words)

    def _transcribe_chunk(self, chunk: AudioChunk) -> list[Word]:
        response = self._client.transcribe(self._payload(chunk))
        cost = float(response.get("usage", {}).get("cost", 0.0))
        self._context.ledger.charge(CostFunction.TRANSCRIPTION, cost)
        return TranscriptionParser().words(response, chunk.offset)

    def _payload(self, chunk: AudioChunk) -> dict[str, Any]:
        settings = self._context.settings
        payload: dict[str, Any] = {
            "model": settings.models.transcriber,
            "input_audio": {
                "data": base64.b64encode(chunk.path.read_bytes()).decode("ascii"),
                "format": "mp3",
            },
            "language": settings.transcription.language,
            "response_format": "verbose_json",
            "timestamp_granularities": ["word"],
        }
        if settings.transcription.hard_words:
            payload["keyterms"] = settings.transcription.hard_words
        return payload


class FakeTranscriber:
    """Test mode: no AI. Every stretch of sound becomes placeholder words, so pauses,
    cuts and render behave like a real run at zero cost."""

    def __init__(self, detector: SilenceDetector) -> None:
        self._detector = detector

    def transcribe(self, audio: Path, duration: float) -> Transcript:
        silences = self._detector.silences(audio, duration)
        words: list[Word] = []
        for start, end in self._speech(silences, duration):
            words.extend(self._fill(start, end, len(words)))
        return Transcript(language="pt", duration=duration, words=words)

    def _speech(self, silences: list[TimeRange], duration: float) -> list[tuple[float, float]]:
        edges = [0.0, *[edge for span in silences for edge in (span.start, span.end)], duration]
        pairs = zip(edges[0::EDGES_PER_RANGE], edges[1::EDGES_PER_RANGE])
        return [(start, end) for start, end in pairs if end - start >= FAKE_WORD_LENGTH]

    def _fill(self, start: float, end: float, first_index: int) -> list[Word]:
        count = max(1, int((end - start) / FAKE_WORD_STEP))
        return [
            Word(
                text=f"fala{first_index + offset}",
                start=start + offset * FAKE_WORD_STEP,
                end=min(end, start + offset * FAKE_WORD_STEP + FAKE_WORD_LENGTH),
            )
            for offset in range(count)
        ]
