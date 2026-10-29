import logging
from pathlib import Path

import pytest

from talkedit.drive import DriveDownloader, DriveLinkParser, HttpReply, VideoSource
from talkedit.errors import ConfigError, DriveNotPublicError, MediaError

FILE_ID = "1l_5RK28JRL19wpT22B-DY9We3TVXnnQQ"
SHARE_LINK = f"https://drive.google.com/file/d/{FILE_ID}/view?usp=sharing"
VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42 fake video"
NOT_FOUND = 404
WARNING_PAGE = (
    '<html><title>Google Drive - Virus scan warning</title><form id="download-form" '
    'action="https://drive.usercontent.google.com/download" method="get">'
    '<input type="submit" value="Download anyway"/>'
    f'<input type="hidden" name="id" value="{FILE_ID}">'
    '<input type="hidden" name="confirm" value="t">'
    '<input type="hidden" name="uuid" value="abc-123"></form></html>'
)


class Replies:
    VIDEO = HttpReply(status=200, content_type="video/mp4", filename="aula.mp4")
    HTML = HttpReply(status=200, content_type="text/html", filename="")


class FakeFetcher:
    """Answers each fetch with the next (reply, body) and remembers the URLs asked."""

    def __init__(self, answers: list[tuple[HttpReply, bytes]], asked: list[str]) -> None:
        self._answers = answers
        self._asked = asked

    def fetch(self, url: str, sink: Path) -> HttpReply:
        self._asked.append(url)
        reply, body = self._answers.pop(0)
        sink.write_bytes(body)
        return reply


class DownloaderFactory:
    def downloader(
        self, answers: list[tuple[HttpReply, bytes]], asked: list[str]
    ) -> DriveDownloader:
        logger = logging.getLogger("teste-drive")
        return DriveDownloader(FakeFetcher(answers, asked), DriveLinkParser(), logger)


class TestDriveLinkParser:
    @pytest.mark.parametrize(
        "link",
        [
            SHARE_LINK,
            f"https://drive.google.com/open?id={FILE_ID}",
            f"https://drive.google.com/uc?id={FILE_ID}&export=download",
            f"https://drive.usercontent.google.com/download?id={FILE_ID}&export=download",
        ],
    )
    def test_every_drive_link_shape_gives_the_file_id(self, link: str) -> None:
        parser = DriveLinkParser()

        file_id = parser.file_id(link)

        assert (parser.is_drive(link), file_id) == (True, FILE_ID)

    def test_folder_link_explains_how_to_get_the_file_link(self) -> None:
        with pytest.raises(ConfigError) as raised:
            DriveLinkParser().file_id("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp")

        assert raised.value.message == "Esse link e de uma pasta do Google Drive, nao de um video."


class TestDriveDownloader:
    def test_public_file_is_saved_with_its_drive_name(self, tmp_path: Path) -> None:
        asked: list[str] = []
        downloader = DownloaderFactory().downloader([(Replies.VIDEO, VIDEO_BYTES)], asked)

        saved = downloader.download(SHARE_LINK, tmp_path)

        assert saved == tmp_path / FILE_ID / "aula.mp4"
        assert saved.read_bytes() == VIDEO_BYTES
        assert "confirm=t" in asked[0], asked

    def test_big_file_warning_page_is_passed_by_its_download_button(self, tmp_path: Path) -> None:
        asked: list[str] = []
        answers = [(Replies.HTML, WARNING_PAGE.encode()), (Replies.VIDEO, VIDEO_BYTES)]
        downloader = DownloaderFactory().downloader(answers, asked)

        saved = downloader.download(SHARE_LINK, tmp_path)

        assert asked[1] == (
            f"https://drive.usercontent.google.com/download?id={FILE_ID}&confirm=t&uuid=abc-123"
        )
        assert saved.read_bytes() == VIDEO_BYTES

    def test_private_file_page_says_how_to_share_it(self, tmp_path: Path) -> None:
        login_page = b"<html><title>Sign in - Google Accounts</title></html>"
        downloader = DownloaderFactory().downloader([(Replies.HTML, login_page)], [])

        with pytest.raises(MediaError) as raised:
            downloader.download(SHARE_LINK, tmp_path)

        assert raised.value.hint == DriveNotPublicError.HINT
        assert list((tmp_path / FILE_ID).iterdir()) == [], "a refused download must leave nothing"

    def test_missing_file_reports_the_drive_error_code(self, tmp_path: Path) -> None:
        gone = HttpReply(status=NOT_FOUND, content_type="", filename="")
        downloader = DownloaderFactory().downloader([(gone, b"")], [])

        with pytest.raises(MediaError) as raised:
            downloader.download(SHARE_LINK, tmp_path)

        assert raised.value.message == (
            "O Google Drive respondeu erro 404: o arquivo nao existe ou nao esta publico."
        )

    def test_same_link_twice_downloads_once(self, tmp_path: Path) -> None:
        asked: list[str] = []
        downloader = DownloaderFactory().downloader([(Replies.VIDEO, VIDEO_BYTES)], asked)
        first = downloader.download(SHARE_LINK, tmp_path)
        (first.parent / "aula_talkedit").mkdir()

        second = downloader.download(SHARE_LINK, tmp_path)

        assert (second, len(asked)) == (first, 1)


class TestVideoSource:
    def test_link_from_another_site_is_refused(self, tmp_path: Path) -> None:
        source = VideoSource(DriveLinkParser(), DownloaderFactory().downloader([], []), tmp_path)

        with pytest.raises(ConfigError) as raised:
            source.local_path("https://www.dropbox.com/s/abc/video.mp4", None)

        assert raised.value.hint == "Baixe o video para o Mac e passe o caminho do arquivo."

    def test_drive_link_goes_to_the_chosen_folder(self, tmp_path: Path) -> None:
        downloader = DownloaderFactory().downloader([(Replies.VIDEO, VIDEO_BYTES)], [])
        source = VideoSource(DriveLinkParser(), downloader, tmp_path / "padrao")

        saved = source.local_path(SHARE_LINK, tmp_path / "escolhida")

        assert saved.parent.parent == (tmp_path / "escolhida").resolve()
