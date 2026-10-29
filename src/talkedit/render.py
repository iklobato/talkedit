import array
import os
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from talkedit.media import CommandRunner, ToolPaths
from talkedit.progress import ProgressReporter
from talkedit.timeline import FrameGrid, FrameSpan, Timeline

FADE_SECONDS = 0.006
FADED_EDGES = 2
X264_THREADS_PER_JOB = 2
SAMPLE_WIDTH_BYTES = 2
PREVIEW_HEIGHT = 360
PREVIEW_CRF = 30
FINAL_AUDIO_BITRATE = "192k"
PREVIEW_AUDIO_BITRATE = "96k"


@dataclass(frozen=True)
class RenderProfile:
    name: str
    height: int
    crf: int
    preset: str
    audio_bitrate: str

    @classmethod
    def final(cls, crf: int, preset: str) -> "RenderProfile":
        return cls("final", 0, crf, preset, FINAL_AUDIO_BITRATE)

    @classmethod
    def preview(cls) -> "RenderProfile":
        return cls("previa", PREVIEW_HEIGHT, PREVIEW_CRF, "ultrafast", PREVIEW_AUDIO_BITRATE)

    def scale_filter(self) -> str:
        return f",scale=-2:{self.height}" if self.height else ""

    def x264_options(self) -> list[str]:
        return ["-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf)]


@dataclass(frozen=True)
class SegmentJob:
    source: Path
    span: FrameSpan
    target: Path


@dataclass(frozen=True)
class MuxJob:
    segments: list[Path]
    audio: Path
    target: Path


class SegmentEncoder:
    """Encodes one kept span. Files are named by span and profile, so a re-render after
    a small change reuses every span that did not move."""

    def __init__(self, runner: CommandRunner, tools: ToolPaths, grid: FrameGrid) -> None:
        self._runner = runner
        self._tools = tools
        self._grid = grid

    def target_for(self, folder: Path, span: FrameSpan, profile: RenderProfile) -> Path:
        return folder / f"{profile.name}_{span.first_frame}_{span.frame_count}.mp4"

    def encode(self, job: SegmentJob, profile: RenderProfile) -> None:
        if job.target.exists():
            return
        partial = job.target.with_name(f"{job.target.stem}.parcial.mp4")
        start = self._grid.seconds_of(job.span.first_frame)
        command = [str(self._tools.ffmpeg), "-hide_banner", "-ss", f"{start:.6f}"]
        command += ["-i", str(job.source), "-an", "-frames:v", str(job.span.frame_count)]
        command += ["-vf", f"fps={self._grid.fps}{profile.scale_filter()}"]
        command += [*profile.x264_options(), "-pix_fmt", "yuv420p"]
        command += ["-threads", str(X264_THREADS_PER_JOB), "-y", str(partial)]
        self._runner.capture(command, job.target.stem)
        partial.replace(job.target)


class AudioSplicer:
    """Joins the kept spans of the clean audio, sample exact to the frame grid. Each join
    gets a 6 ms fade out and fade in, which removes clicks without an audible dip."""

    def __init__(self, grid: FrameGrid) -> None:
        self._grid = grid

    def splice(self, clean_audio: Path, timeline: Timeline, target: Path) -> None:
        with wave.open(str(clean_audio), "rb") as reader:
            rate = reader.getframerate()
            samples = array.array("h", reader.readframes(reader.getnframes()))
        spliced = array.array("h")
        for span in timeline.spans:
            spliced.extend(self._piece(samples, span, rate))
        with wave.open(str(target), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(SAMPLE_WIDTH_BYTES)
            writer.setframerate(rate)
            writer.writeframes(spliced.tobytes())

    def _piece(self, samples: array.array, span: FrameSpan, rate: int) -> array.array:
        start = self._grid.sample_at(span.first_frame, rate)
        end = self._grid.sample_at(span.end_frame, rate)
        piece = samples[start:end]
        piece.extend([0] * (end - start - len(piece)))
        fade = min(int(rate * FADE_SECONDS), len(piece) // FADED_EDGES)
        for index in range(fade):
            gain = index / fade
            piece[index] = int(piece[index] * gain)
            piece[-1 - index] = int(piece[-1 - index] * gain)
        return piece


class ConcatMuxer:
    def __init__(self, runner: CommandRunner, tools: ToolPaths) -> None:
        self._runner = runner
        self._tools = tools

    def mux(self, job: MuxJob, profile: RenderProfile) -> None:
        job.target.parent.mkdir(parents=True, exist_ok=True)
        listing = job.audio.with_name(f"lista_{profile.name}.txt")
        listing.write_text("".join(self._entry(path) for path in job.segments), encoding="utf-8")
        command = [str(self._tools.ffmpeg), "-hide_banner", "-f", "concat", "-safe", "0"]
        command += ["-i", str(listing), "-i", str(job.audio), "-map", "0:v", "-map", "1:a"]
        command += ["-c:v", "copy", "-c:a", "aac", "-b:a", profile.audio_bitrate, "-ac", "2"]
        command += ["-movflags", "+faststart", "-y", str(job.target)]
        self._runner.capture(command, f"montagem-{profile.name}")

    def _entry(self, path: Path) -> str:
        escaped = str(path).replace("'", "'\\''")
        return f"file '{escaped}'\n"


@dataclass(frozen=True)
class RenderRequest:
    source: Path
    clean_audio: Path
    timeline: Timeline
    work_folder: Path
    target: Path


class Renderer:
    def __init__(self, encoder: SegmentEncoder, splicer: AudioSplicer, muxer: ConcatMuxer) -> None:
        self._encoder = encoder
        self._splicer = splicer
        self._muxer = muxer

    def render(
        self, request: RenderRequest, profile: RenderProfile, progress: ProgressReporter
    ) -> None:
        request.work_folder.mkdir(parents=True, exist_ok=True)
        jobs = [
            SegmentJob(
                request.source, span, self._encoder.target_for(request.work_folder, span, profile)
            )
            for span in request.timeline.spans
        ]
        self._encode_all(jobs, profile, progress)
        audio = request.work_folder / f"audio_{profile.name}.wav"
        self._splicer.splice(request.clean_audio, request.timeline, audio)
        segments = [job.target for job in jobs]
        self._muxer.mux(MuxJob(segments, audio, request.target), profile)

    def _encode_all(
        self, jobs: list[SegmentJob], profile: RenderProfile, progress: ProgressReporter
    ) -> None:
        progress.start_task()
        workers = max(1, (os.cpu_count() or 1) // X264_THREADS_PER_JOB)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = [pool.submit(self._encoder.encode, job, profile) for job in jobs]
            for done, future in enumerate(as_completed(pending), 1):
                future.result()
                progress.step(done, len(pending))
