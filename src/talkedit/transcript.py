from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

LAUGHTER_MARKERS = ("laugh", "ris", "gargalh")
HALVES = 2


class TokenKind(Enum):
    WORD = "word"
    EVENT = "audio_event"


class Word(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    kind: TokenKind = TokenKind.WORD

    def is_laughter(self) -> bool:
        lowered = self.text.lower()
        return self.kind is TokenKind.EVENT and any(mark in lowered for mark in LAUGHTER_MARKERS)

    def middle(self) -> float:
        return (self.start + self.end) / HALVES


class Transcript(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: str
    duration: float
    words: list[Word]

    def text_between(self, first: int, last: int) -> str:
        return " ".join(word.text for word in self.words[first : last + 1])

    def overlapping(self, start: float, end: float) -> list[Word]:
        return [word for word in self.words if word.start < end and word.end > start]
