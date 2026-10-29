from dataclasses import dataclass
from types import MappingProxyType

from talkedit.plan import Cut, CutKind, CutSource, TimeRange
from talkedit.settings import Pace
from talkedit.transcript import Transcript, Word


@dataclass(frozen=True)
class PaceProfile:
    """A pause longer than `max_gap` shrinks to `tail` after the last word plus
    `lead` before the next one. Cut points always sit inside the silence, never in a word."""

    max_gap: float
    lead: float
    tail: float


class PaceProfiles:
    # ponytail: fixed padding around STT word times; refine cut points to the quietest
    # sample in the gap if a real recording shows clipped word endings.
    PROFILES = MappingProxyType(
        {
            Pace.NATURAL: PaceProfile(max_gap=0.9, lead=0.15, tail=0.25),
            Pace.DYNAMIC: PaceProfile(max_gap=0.3, lead=0.08, tail=0.14),
            Pace.FAST: PaceProfile(max_gap=0.2, lead=0.05, tail=0.10),
        }
    )

    def for_pace(self, pace: Pace) -> PaceProfile:
        return self.PROFILES[pace]


@dataclass(frozen=True)
class Gap:
    start: float
    end: float

    def length(self) -> float:
        return self.end - self.start

    def touches(self, protected: list[TimeRange]) -> bool:
        return any(span.start < self.end and span.end > self.start for span in protected)


class PauseCutter:
    def __init__(self, profile: PaceProfile) -> None:
        self._profile = profile

    def cuts(self, transcript: Transcript, protected: list[TimeRange]) -> list[Cut]:
        gaps = self._gaps(sorted(transcript.words, key=lambda word: word.start), transcript)
        long_gaps = [gap for gap in gaps if self._is_cuttable(gap, protected)]
        return [self._cut(index, gap) for index, gap in enumerate(long_gaps)]

    def _gaps(self, words: list[Word], transcript: Transcript) -> list[Gap]:
        if not words:
            return []
        gaps = [Gap(0.0 - self._profile.tail, words[0].start)]
        speech_end = words[0].end
        for word in words[1:]:
            gaps.append(Gap(speech_end, word.start))
            speech_end = max(speech_end, word.end)
        gaps.append(Gap(speech_end, transcript.duration + self._profile.lead))
        return gaps

    def _is_cuttable(self, gap: Gap, protected: list[TimeRange]) -> bool:
        return gap.length() > self._profile.max_gap and not gap.touches(protected)

    def _cut(self, index: int, gap: Gap) -> Cut:
        return Cut(
            id=f"p{index}",
            start=max(0.0, gap.start + self._profile.tail),
            end=gap.end - self._profile.lead,
            kind=CutKind.PAUSE,
            source=CutSource.PACING,
            reason="pausa longa encurtada",
        )
