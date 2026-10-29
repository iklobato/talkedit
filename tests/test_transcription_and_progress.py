import logging
import threading
from typing import Any

import pytest

from talkedit.errors import AIResponseError
from talkedit.openrouter import ChatRequest, OpenRouterClient
from talkedit.plan import TimeRange
from talkedit.progress import ProgressReporter
from talkedit.transcript import TokenKind
from talkedit.transcription import (
    CHUNK_SEARCH_SECONDS,
    CHUNK_SECONDS,
    ChunkBoundaries,
    TranscriptionParser,
)


class TestChunkBoundaries:
    DURATION = 300.0
    SILENCE_NEAR_FIRST_TARGET = TimeRange(start=125.0, end=127.0)
    SILENCE_TOO_FAR = TimeRange(start=180.0, end=181.0)

    def test_boundary_moves_to_the_middle_of_the_nearest_silence(self) -> None:
        silences = [self.SILENCE_NEAR_FIRST_TARGET]

        points = ChunkBoundaries().boundaries(silences, self.DURATION)

        assert points[1] == self.SILENCE_NEAR_FIRST_TARGET.middle(), points

    def test_without_nearby_silence_the_boundary_stays_on_target(self) -> None:
        points = ChunkBoundaries().boundaries([self.SILENCE_TOO_FAR], self.DURATION)

        assert points[1] == CHUNK_SECONDS, points
        assert abs(self.SILENCE_TOO_FAR.middle() - CHUNK_SECONDS) > CHUNK_SEARCH_SECONDS

    def test_boundaries_cover_the_whole_audio(self) -> None:
        points = ChunkBoundaries().boundaries([], self.DURATION)

        assert (points[0], points[-1]) == (0.0, self.DURATION), points


class TestTranscriptionParser:
    OFFSET = 120.0
    WORD = {"word": " oi ", "start": 1.0, "end": 1.4}
    LAUGH = {"word": "(risos)", "start": 2.0, "end": 3.0, "type": "audio_event"}
    SPACE = {"word": " ", "start": 1.4, "end": 1.5}

    def test_words_are_shifted_by_chunk_offset_and_events_kept(self) -> None:
        response = {"words": [self.WORD, self.SPACE, self.LAUGH]}

        words = TranscriptionParser().words(response, self.OFFSET)

        assert [(word.text, word.start, word.kind) for word in words] == [
            ("oi", self.OFFSET + self.WORD["start"], TokenKind.WORD),
            ("(risos)", self.OFFSET + self.LAUGH["start"], TokenKind.EVENT),
        ]
        assert words[1].is_laughter()

    def test_response_without_word_times_names_a_model_that_has_them(self) -> None:
        with pytest.raises(AIResponseError) as raised:
            TranscriptionParser().words({"text": "oi"}, self.OFFSET)

        assert (
            raised.value.hint == "Use um modelo com tempo por palavra, como elevenlabs/scribe-v2."
        )


class FakeTransport:
    def __init__(self, response: dict[str, Any], sent: list[dict[str, Any]]) -> None:
        self._response = response
        self._sent = sent

    def post_json(self, url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        self._sent.append({"url": url, "payload": payload})
        return self._response


class TestOpenRouterClient:
    COST = 0.0123

    def request(self) -> ChatRequest:
        return ChatRequest(
            "m", "sistema", [{"type": "text", "text": "oi"}], "plano", {"type": "object"}
        )

    def test_chat_parses_json_content_and_reports_cost(self) -> None:
        response = {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"cost": self.COST},
        }
        sent: list[dict[str, Any]] = []

        reply = OpenRouterClient("chave", FakeTransport(response, sent)).chat(self.request())

        assert (reply.content, reply.cost) == ({"ok": True}, self.COST)
        assert sent[0]["payload"]["response_format"]["json_schema"]["strict"] is True

    def test_chat_reply_that_is_not_json_raises_a_clear_error(self) -> None:
        response = {"choices": [{"message": {"content": "nao sei"}}]}

        with pytest.raises(AIResponseError) as raised:
            OpenRouterClient("chave", FakeTransport(response, [])).chat(self.request())

        assert raised.value.hint == "Rode talkedit continuar para tentar de novo."


class FakeClock:
    def __init__(self, times: list[float]) -> None:
        self._times = times

    def now(self) -> float:
        return self._times.pop(0)


class TestProgressReporter:
    STARTED = 1000.0
    HALF_DONE = 1060.0
    TOTAL = 10
    DONE = 5

    def test_time_left_comes_from_the_pace_since_the_task_started(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("teste-progresso")
        reporter = ProgressReporter(
            logger, FakeClock([self.STARTED, self.HALF_DONE]), threading.Lock()
        )
        reporter.start_task()

        with caplog.at_level(logging.INFO, logger="teste-progresso"):
            reporter.step(self.DONE, self.TOTAL)

        assert caplog.messages == ["    5 de 10 (faltam ~1 min)"], caplog.messages
