from dataclasses import dataclass
from fractions import Fraction

from talkedit.plan import Cut

MIN_KEEP_FRAMES = 3


@dataclass(frozen=True)
class FrameSpan:
    """A kept piece of the source, in whole frames so audio and video stay in sync."""

    first_frame: int
    frame_count: int

    @property
    def end_frame(self) -> int:
        return self.first_frame + self.frame_count


class FrameGrid:
    def __init__(self, fps: Fraction) -> None:
        self._fps = fps

    @property
    def fps(self) -> Fraction:
        return self._fps

    def frame_at(self, seconds: float) -> int:
        return round(Fraction(seconds) * self._fps)

    def seconds_of(self, frame: int) -> float:
        return float(frame / self._fps)

    def sample_at(self, frame: int, sample_rate: int) -> int:
        return round(frame * sample_rate / self._fps)


@dataclass(frozen=True)
class Timeline:
    spans: tuple[FrameSpan, ...]
    fps: Fraction

    def total_frames(self) -> int:
        return sum(span.frame_count for span in self.spans)

    def total_seconds(self) -> float:
        return float(self.total_frames() / self.fps)


class TimelineBuilder:
    def __init__(self, grid: FrameGrid) -> None:
        self._grid = grid

    def build(self, duration: float, cuts: list[Cut]) -> Timeline:
        removed = self._merge([(max(0.0, cut.start), min(duration, cut.end)) for cut in cuts])
        spans = [self._snap(start, end) for start, end in self._complement(duration, removed)]
        kept = tuple(span for span in spans if span.frame_count >= MIN_KEEP_FRAMES)
        return Timeline(spans=kept, fps=self._grid.fps)

    def _merge(self, ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
        merged: list[tuple[float, float]] = []
        for start, end in sorted(span for span in ranges if span[1] > span[0]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                continue
            merged.append((start, end))
        return merged

    def _complement(
        self, duration: float, removed: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        kept: list[tuple[float, float]] = []
        cursor = 0.0
        for start, end in removed:
            kept.append((cursor, start))
            cursor = end
        kept.append((cursor, duration))
        return [(start, end) for start, end in kept if end > start]

    def _snap(self, start: float, end: float) -> FrameSpan:
        first = self._grid.frame_at(start)
        return FrameSpan(first_frame=first, frame_count=self._grid.frame_at(end) - first)
