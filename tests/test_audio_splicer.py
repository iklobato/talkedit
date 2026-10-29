import array
import wave
from fractions import Fraction
from pathlib import Path

from talkedit.render import FADE_SECONDS, AudioSplicer
from talkedit.timeline import FrameGrid, FrameSpan, Timeline


class TestAudioSplicer:
    FPS = Fraction(25)
    RATE = 48000
    LOUD = 10000
    SECONDS = 4
    FIRST = FrameSpan(0, 25)
    SECOND = FrameSpan(50, 25)
    MIDDLE_FRAME = 12

    def write_constant_wav(self, path: Path) -> None:
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(array.array("h").itemsize)
            writer.setframerate(self.RATE)
            writer.writeframes(array.array("h", [self.LOUD] * (self.RATE * self.SECONDS)).tobytes())

    def read_samples(self, path: Path) -> array.array:
        with wave.open(str(path), "rb") as reader:
            return array.array("h", reader.readframes(reader.getnframes()))

    def splice(self, tmp_path: Path) -> array.array:
        source, target = tmp_path / "limpo.wav", tmp_path / "editado.wav"
        self.write_constant_wav(source)
        timeline = Timeline(spans=(self.FIRST, self.SECOND), fps=self.FPS)
        AudioSplicer(FrameGrid(self.FPS)).splice(source, timeline, target)
        return self.read_samples(target)

    def test_length_matches_kept_frames_exactly(self, tmp_path: Path) -> None:
        samples = self.splice(tmp_path)

        kept_frames = self.FIRST.frame_count + self.SECOND.frame_count
        assert len(samples) == kept_frames * self.RATE / self.FPS, "audio would drift from video"

    def test_join_is_silent_and_middle_is_untouched(self, tmp_path: Path) -> None:
        samples = self.splice(tmp_path)

        join = self.FIRST.frame_count * self.RATE // self.FPS
        fade = int(self.RATE * FADE_SECONDS)
        assert samples[join - 1] < self.LOUD // fade + 1, "end of first piece must fade out"
        assert samples[join] == 0, "start of second piece must fade in from zero"
        middle = self.MIDDLE_FRAME * self.RATE // self.FPS
        assert samples[middle] == self.LOUD, "audio away from the join must not change"
