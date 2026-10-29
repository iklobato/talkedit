from enum import Enum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

SECONDS_PER_MINUTE = 60
HALVES = 2


class CutKind(Enum):
    PAUSE = "pausa"
    REPEATED_TAKE = "take_repetido"
    ABANDONED = "frase_abandonada"
    EDIT_COMMAND = "comando_de_edicao"
    BEFORE_START = "antes_de_comecar"
    AFTER_END = "depois_de_terminar"
    VISUAL = "momento_visual_ruim"
    OTHER = "outro"
    MANUAL = "manual"


class CutSource(Enum):
    PACING = "ritmo"
    EDITOR = "editora"
    REVIEWER = "revisora"
    USER = "voce"


class CutStatus(Enum):
    APPLIED = "aplicado"
    RESTORED = "devolvido"
    SUGGESTED = "sugerido"


class TimeLabel:
    def format(self, seconds: float) -> str:
        minutes, rest = divmod(int(seconds), SECONDS_PER_MINUTE)
        return f"{minutes:02d}:{rest:02d}"


class CutDescriber:
    """Plain Portuguese line, e.g. "02:14 a 02:31, 'entao...', take repetido, <motivo>"."""

    LABELS = MappingProxyType(
        {
            CutKind.PAUSE: "pausa",
            CutKind.REPEATED_TAKE: "take repetido",
            CutKind.ABANDONED: "frase abandonada",
            CutKind.EDIT_COMMAND: "comando para a edicao",
            CutKind.BEFORE_START: "conversa antes de comecar",
            CutKind.AFTER_END: "conversa depois de terminar",
            CutKind.VISUAL: "momento visual ruim",
            CutKind.OTHER: "outro motivo",
            CutKind.MANUAL: "marcado por voce",
        }
    )

    def __init__(self, time_label: TimeLabel) -> None:
        self._time_label = time_label

    def kind_label(self, kind: CutKind) -> str:
        return self.LABELS[kind]

    def describe(self, cut: "Cut") -> str:
        quoted = f"'{cut.text}'" if cut.text else "sem fala"
        span = f"{self._time_label.format(cut.start)} a {self._time_label.format(cut.end)}"
        return f"{span}, {quoted}, {self.kind_label(cut.kind)}, {cut.reason}"


class Cut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    kind: CutKind
    source: CutSource
    status: CutStatus = CutStatus.APPLIED
    text: str = ""
    reason: str = ""
    notes: list[str] = []

    def is_applied(self) -> bool:
        return self.status is CutStatus.APPLIED

    def is_pause(self) -> bool:
        return self.kind is CutKind.PAUSE

    def duration(self) -> float:
        return self.end - self.start

    def overlaps(self, start: float, end: float) -> bool:
        return self.start < end and self.end > start

    def with_status(self, status: CutStatus, note: str) -> "Cut":
        return self.model_copy(update={"status": status, "notes": [*self.notes, note]})



class Emphasis(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    reason: str


class TimeRange(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: float = Field(ge=0)
    end: float = Field(ge=0)

    def middle(self) -> float:
        return (self.start + self.end) / HALVES


class EditPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    cuts: list[Cut]
    emphasis: list[Emphasis] = []
    protected: list[TimeRange] = []
    notes: list[str] = []

    def applied(self) -> list[Cut]:
        return [cut for cut in self.cuts if cut.is_applied()]

    def replacing(self, cuts: list[Cut]) -> "EditPlan":
        return self.model_copy(update={"cuts": cuts})

    def with_notes(self, notes: list[str]) -> "EditPlan":
        return self.model_copy(update={"notes": [*self.notes, *notes]})
