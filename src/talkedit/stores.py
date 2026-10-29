from pathlib import Path

from pydantic import ValidationError

from talkedit.errors import ProjectError
from talkedit.plan import EditPlan
from talkedit.transcript import Transcript

JSON_INDENT = 2


class TranscriptStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, transcript: Transcript) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(transcript.model_dump_json(indent=JSON_INDENT), encoding="utf-8")

    def load(self) -> Transcript:
        try:
            return Transcript.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise ProjectError(
                f"Nao consegui ler a transcricao em {self._path}.",
                "Refaca a transcricao com: talkedit refazer <pasta> transcricao",
            ) from error


class PlanStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, plan: EditPlan) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(plan.model_dump_json(indent=JSON_INDENT), encoding="utf-8")
        temporary.replace(self._path)

    def load(self) -> EditPlan:
        try:
            return EditPlan.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise ProjectError(
                f"Nao consegui ler o plano de edicao em {self._path}.",
                "Refaca o plano com: talkedit refazer <pasta> plano",
            ) from error
