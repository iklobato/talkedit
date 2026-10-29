from pathlib import Path

from talkedit.media import CommandRunner, ToolPaths

PROXY_HEIGHT = 360
PROXY_FPS = 1
PROXY_CRF = 34


class ProxyMaker:
    """Light copy of the video for the AI: 360p, 1 frame per second, no sound. Only key
    frames are decoded, so a 4K phone video is read fast on an Intel Mac."""

    def __init__(self, runner: CommandRunner, tools: ToolPaths) -> None:
        self._runner = runner
        self._tools = tools

    def make(self, source: Path, target: Path) -> None:
        command = [str(self._tools.ffmpeg), "-hide_banner", "-skip_frame", "nokey"]
        command += ["-i", str(source), "-an"]
        command += ["-vf", f"fps={PROXY_FPS},scale=-2:{PROXY_HEIGHT}"]
        command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(PROXY_CRF)]
        command += ["-pix_fmt", "yuv420p", "-y", str(target)]
        self._runner.capture(command, "proxy")


class PlayerMaker:
    """Copy for the review page player: 540p H.264 with the clean audio. Browsers on an
    Intel Mac may not play the phone original (HEVC, 4K), and this one seeks fast."""

    HEIGHT = 540
    CRF = 26
    AUDIO_BITRATE = "128k"

    def __init__(self, runner: CommandRunner, tools: ToolPaths) -> None:
        self._runner = runner
        self._tools = tools

    def make(self, source: Path, clean_audio: Path, target: Path) -> None:
        command = [str(self._tools.ffmpeg), "-hide_banner", "-i", str(source)]
        command += ["-i", str(clean_audio), "-map", "0:v:0", "-map", "1:a:0"]
        command += ["-vf", f"scale=-2:{self.HEIGHT}", "-pix_fmt", "yuv420p"]
        command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(self.CRF)]
        command += ["-c:a", "aac", "-b:a", self.AUDIO_BITRATE, "-ac", "2"]
        command += ["-movflags", "+faststart", "-y", str(target)]
        self._runner.capture(command, "player")
