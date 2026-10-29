from builders import TranscriptBuilder

from talkedit.pacing import PaceProfile, PaceProfiles, PauseCutter
from talkedit.plan import TimeRange
from talkedit.settings import Pace


class TestPauseCutter:
    MAX_GAP = 0.3
    LEAD = 0.08
    TAIL = 0.14
    FIRST_END = 0.5
    LONG_GAP_NEXT = 2.0
    SHORT_GAP_NEXT = 0.75
    WORD_LENGTH = 0.5
    LATE_START = 3.0
    END_OF_VIDEO = 6.0
    PRECISION = 9
    THREE_WORDS = (("um", 0.0, 0.4), ("dois", 1.4, 1.9), ("tres", 3.0, 3.6))

    def cutter(self) -> PauseCutter:
        return PauseCutter(PaceProfile(max_gap=self.MAX_GAP, lead=self.LEAD, tail=self.TAIL))

    def two_words(self, next_start: float) -> tuple[tuple[str, float, float], ...]:
        return (("oi", 0.0, self.FIRST_END), ("gente", next_start, next_start + self.WORD_LENGTH))

    def test_long_pause_shrinks_to_tail_plus_lead(self) -> None:
        words = self.two_words(self.LONG_GAP_NEXT)
        transcript = TranscriptBuilder().build(words, self.LONG_GAP_NEXT + self.WORD_LENGTH)

        cuts = self.cutter().cuts(transcript, protected=[])

        spans = [(round(cut.start, self.PRECISION), round(cut.end, self.PRECISION)) for cut in cuts]
        expected = (self.FIRST_END + self.TAIL, self.LONG_GAP_NEXT - self.LEAD)
        assert spans == [expected], f"pause should become tail+lead, got {spans}"

    def test_short_pause_is_kept(self) -> None:
        words = self.two_words(self.SHORT_GAP_NEXT)
        transcript = TranscriptBuilder().build(words, self.SHORT_GAP_NEXT + self.WORD_LENGTH)

        cuts = self.cutter().cuts(transcript, protected=[])

        assert cuts == [], f"a pause under max_gap must stay, got {cuts}"

    def test_cut_never_enters_a_word(self) -> None:
        transcript = TranscriptBuilder().build(self.THREE_WORDS, duration=self.END_OF_VIDEO)

        cuts = self.cutter().cuts(transcript, protected=[])

        for cut in cuts:
            inside = [word.text for word in transcript.overlapping(cut.start, cut.end)]
            assert inside == [], f"cut {cut.start}-{cut.end} enters words {inside}"

    def test_protected_dramatic_pause_is_not_cut(self) -> None:
        words = self.two_words(self.LONG_GAP_NEXT)
        transcript = TranscriptBuilder().build(words, self.LONG_GAP_NEXT + self.WORD_LENGTH)
        dramatic = [TimeRange(start=self.FIRST_END, end=self.LONG_GAP_NEXT)]

        cuts = self.cutter().cuts(transcript, protected=dramatic)

        assert cuts == [], f"protected pause was cut: {cuts}"

    def test_silence_before_first_word_and_after_last_is_cut(self) -> None:
        late_end = self.LATE_START + self.WORD_LENGTH
        transcript = TranscriptBuilder().build(
            (("oi", self.LATE_START, late_end),), duration=self.END_OF_VIDEO
        )

        cuts = self.cutter().cuts(transcript, protected=[])

        spans = [(round(cut.start, self.PRECISION), round(cut.end, self.PRECISION)) for cut in cuts]
        before = (0.0, round(self.LATE_START - self.LEAD, self.PRECISION))
        after = (round(late_end + self.TAIL, self.PRECISION), self.END_OF_VIDEO)
        assert spans == [before, after], spans


class TestPaceProfiles:
    def test_natural_pace_keeps_more_pause_than_dynamic(self) -> None:
        profiles = PaceProfiles()

        natural, dynamic = profiles.for_pace(Pace.NATURAL), profiles.for_pace(Pace.DYNAMIC)

        assert natural.max_gap > dynamic.max_gap
        assert natural.lead + natural.tail > dynamic.lead + dynamic.tail
