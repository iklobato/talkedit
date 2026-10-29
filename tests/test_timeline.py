from fractions import Fraction

from builders import CutBuilder

from talkedit.timeline import MIN_KEEP_FRAMES, FrameGrid, FrameSpan, TimelineBuilder


class TestTimelineBuilder:
    FPS = Fraction(30)
    DURATION = 10.0
    FIRST_CUT = (2.0, 3.0)
    SECOND_CUT = (5.0, 6.5)
    OVERLAPPING = (3.0, 5.0)

    def builder(self) -> TimelineBuilder:
        return TimelineBuilder(FrameGrid(self.FPS))

    def frame(self, seconds: float) -> int:
        return int(seconds * self.FPS)

    def test_kept_spans_are_the_complement_of_cuts_on_whole_frames(self) -> None:
        cuts = [CutBuilder().pause(*self.FIRST_CUT), CutBuilder().pause(*self.SECOND_CUT)]

        timeline = self.builder().build(self.DURATION, cuts)

        expected = (
            FrameSpan(0, self.frame(self.FIRST_CUT[0])),
            FrameSpan(
                self.frame(self.FIRST_CUT[1]), self.frame(self.SECOND_CUT[0] - self.FIRST_CUT[1])
            ),
            FrameSpan(
                self.frame(self.SECOND_CUT[1]), self.frame(self.DURATION - self.SECOND_CUT[1])
            ),
        )
        assert timeline.spans == expected, timeline.spans

    def test_overlapping_cuts_are_merged_into_one_gap(self) -> None:
        cuts = [CutBuilder().pause(*self.FIRST_CUT), CutBuilder().pause(*self.OVERLAPPING)]

        timeline = self.builder().build(self.DURATION, cuts)

        starts = [span.first_frame for span in timeline.spans]
        assert starts == [0, self.frame(self.OVERLAPPING[1])], timeline.spans

    def test_slivers_shorter_than_the_minimum_are_dropped(self) -> None:
        sliver_end = self.FIRST_CUT[1] + float((MIN_KEEP_FRAMES - 1) / self.FPS)
        cuts = [
            CutBuilder().pause(*self.FIRST_CUT),
            CutBuilder().pause(sliver_end, self.SECOND_CUT[1]),
        ]

        timeline = self.builder().build(self.DURATION, cuts)

        starts = [span.first_frame for span in timeline.spans]
        assert starts == [0, self.frame(self.SECOND_CUT[1])], timeline.spans

    def test_total_seconds_is_kept_frames_over_fps(self) -> None:
        timeline = self.builder().build(self.DURATION, [CutBuilder().pause(*self.FIRST_CUT)])

        removed = self.FIRST_CUT[1] - self.FIRST_CUT[0]
        assert timeline.total_seconds() == self.DURATION - removed


class TestFrameGrid:
    NTSC = Fraction(30000, 1001)
    SAMPLE_RATE = 48000
    ONE_THOUSAND_AND_ONE_SECONDS_OF_FRAMES = 30000

    def test_audio_samples_follow_ntsc_frames_without_drift(self) -> None:
        grid = FrameGrid(self.NTSC)

        samples = grid.sample_at(self.ONE_THOUSAND_AND_ONE_SECONDS_OF_FRAMES, self.SAMPLE_RATE)

        seconds = self.ONE_THOUSAND_AND_ONE_SECONDS_OF_FRAMES / self.NTSC
        assert samples == seconds * self.SAMPLE_RATE, "audio and video must cover the same time"
