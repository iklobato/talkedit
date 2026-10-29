import json
import logging
import os
import shlex
from pathlib import Path

from talkedit.app import UserHome
from talkedit.cli import CommandLine, ParserFactory
from talkedit.media import ToolPaths
from talkedit.workspace import ProjectWorkspace


class SampleVideo:
    """12 s at 29.97 fps: a 220 Hz tone for 1.5 s, then 1.5 s of silence, repeated."""

    SECONDS = 12
    TONE = r"'0.3*sin(2*PI*220*t)*lt(mod(t\,3)\,1.5)'"

    def make(self, target: Path) -> None:
        ffmpeg = str(ToolPaths.bundled().ffmpeg)
        command = [ffmpeg, "-nostdin", "-loglevel", "error", "-f", "lavfi"]
        command += ["-i", f"testsrc2=size=320x240:rate=30000/1001:duration={self.SECONDS}"]
        command += ["-f", "lavfi", "-i", f"aevalsrc={self.TONE}:s=48000:d={self.SECONDS}"]
        command += ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-y", str(target)]
        assert os.system(shlex.join(command)) == 0, "could not build the sample video"


class MediaDurations:
    def read(self, video: Path, report: Path) -> dict[str, float]:
        ffprobe = str(ToolPaths.bundled().ffprobe)
        command = [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,duration"]
        command += ["-of", "json", str(video)]
        assert os.system(f"{shlex.join(command)} > {shlex.quote(str(report))}") == 0
        streams = json.loads(report.read_text())["streams"]
        return {stream["codec_type"]: float(stream["duration"]) for stream in streams}


class TestTestModeEndToEnd:
    ONE_FRAME = 1001 / 30000
    EXIT_OK = 0

    def test_plan_then_approve_delivers_a_shorter_video_in_sync(self, tmp_path: Path) -> None:
        source = tmp_path / "bruto.mp4"
        SampleVideo().make(source)
        cli = CommandLine(ParserFactory().parser(), UserHome(tmp_path / "home"))
        logging.getLogger("talkedit").handlers.clear()

        planned = cli.main(["editar", str(source), "--teste"])
        approved = cli.main(["aprovar", str(source)])

        workspace = ProjectWorkspace.beside(source)
        durations = MediaDurations().read(workspace.youtube_video, tmp_path / "probe.json")
        assert (planned, approved) == (self.EXIT_OK, self.EXIT_OK)
        assert abs(durations["video"] - durations["audio"]) < self.ONE_FRAME, durations
        assert durations["video"] < SampleVideo.SECONDS, f"nothing was cut: {durations}"
        assert "## Trechos removidos" in workspace.report_file.read_text(encoding="utf-8")

    def test_second_edit_of_the_same_video_points_to_continue(self, tmp_path: Path) -> None:
        source = tmp_path / "bruto.mp4"
        SampleVideo().make(source)
        cli = CommandLine(ParserFactory().parser(), UserHome(tmp_path / "home"))

        cli.main(["editar", str(source), "--teste"])
        again = cli.main(["editar", str(source), "--teste"])

        assert again != self.EXIT_OK, "a second edit must not overwrite the project"
