from dataclasses import dataclass

from talkedit.plan import TimeLabel
from talkedit.transcript import Transcript

SENTENCE_END = (".", "?", "!", "…")
PHRASE_BREAK_SECONDS = 0.7
MAX_PHRASE_WORDS = 25


@dataclass(frozen=True)
class Phrase:
    first: int
    last: int
    start: float
    end: float
    text: str


class PhraseGrouper:
    """Groups word indexes into phrases for prompts: a sentence end, a long silence or
    a very long run of words closes a phrase."""

    def group(self, transcript: Transcript) -> list[Phrase]:
        phrases: list[Phrase] = []
        first = 0
        for index in range(len(transcript.words)):
            if self._closes(transcript, index, index - first + 1):
                phrases.append(self._phrase(transcript, first, index))
                first = index + 1
        return phrases

    def _closes(self, transcript: Transcript, index: int, length: int) -> bool:
        words = transcript.words
        if index == len(words) - 1 or length >= MAX_PHRASE_WORDS:
            return True
        gap = words[index + 1].start - words[index].end
        return words[index].text.endswith(SENTENCE_END) or gap > PHRASE_BREAK_SECONDS

    def _phrase(self, transcript: Transcript, first: int, last: int) -> Phrase:
        return Phrase(
            first=first,
            last=last,
            start=transcript.words[first].start,
            end=transcript.words[last].end,
            text=transcript.text_between(first, last),
        )


class PhraseListing:
    """One phrase per line: "[w12-w30] 00:14-00:19 | texto"."""

    def __init__(self, label: TimeLabel) -> None:
        self._label = label

    def lines(self, phrases: list[Phrase]) -> str:
        return "\n".join(self._line(phrase) for phrase in phrases)

    def _line(self, phrase: Phrase) -> str:
        span = f"{self._label.format(phrase.start)}-{self._label.format(phrase.end)}"
        return f"[w{phrase.first}-w{phrase.last}] {span} | {phrase.text}"
