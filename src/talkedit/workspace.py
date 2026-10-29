from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ValidationError

from talkedit.errors import ProjectError

PROJECT_SUFFIX = "_talkedit"
JSON_INDENT = 2


class RunMode(Enum):
    REAL = "real"
    TEST = "teste"


class Stage(Enum):
    CLEAN_AUDIO = "audio"
    TRANSCRIBE = "transcricao"
    PROXY = "proxy"
    PLAYER = "player"
    PLAN = "plano"
    REVIEW = "revisao"
    RENDER = "render"


STAGE_ORDER = (
    Stage.CLEAN_AUDIO,
    Stage.TRANSCRIBE,
    Stage.PROXY,
    Stage.PLAYER,
    Stage.PLAN,
    Stage.REVIEW,
    Stage.RENDER,
)


@dataclass(frozen=True)
class ProjectWorkspace:
    """One folder per video. The source video is only ever read."""

    root: Path

    @classmethod
    def beside(cls, source: Path) -> "ProjectWorkspace":
        return cls(source.parent / f"{source.stem}{PROJECT_SUFFIX}")

    @property
    def state_file(self) -> Path:
        return self.root / "estado.json"

    @property
    def work_dir(self) -> Path:
        return self.root / "trabalho"

    @property
    def logs_dir(self) -> Path:
        return self.work_dir / "logs"

    @property
    def delivery_dir(self) -> Path:
        return self.root / "entrega"

    @property
    def clean_audio(self) -> Path:
        return self.work_dir / "audio_limpo.wav"

    @property
    def proxy_video(self) -> Path:
        return self.work_dir / "proxy.mp4"

    @property
    def player_video(self) -> Path:
        return self.work_dir / "player.mp4"

    @property
    def transcript_file(self) -> Path:
        return self.work_dir / "transcricao.json"

    @property
    def plan_file(self) -> Path:
        return self.work_dir / "plano.json"

    @property
    def costs_file(self) -> Path:
        return self.work_dir / "custos.json"

    @property
    def segments_dir(self) -> Path:
        return self.work_dir / "segmentos"

    @property
    def youtube_video(self) -> Path:
        return self.delivery_dir / "youtube.mp4"

    @property
    def preview_video(self) -> Path:
        return self.work_dir / "previa.mp4"

    @property
    def report_file(self) -> Path:
        return self.delivery_dir / "relatorio.md"


class ProjectState(BaseModel):
    source: str
    mode: RunMode = RunMode.REAL
    overrides: list[str] = []
    completed: list[Stage] = []
    approved: bool = False
    editor_request: str = ""

    def is_done(self, stage: Stage) -> bool:
        return stage in self.completed

    def mark_done(self, stage: Stage) -> "ProjectState":
        return self.model_copy(update={"completed": [*self.completed, stage]})

    def approve(self) -> "ProjectState":
        return self.model_copy(update={"approved": True})

    def reopen_from(self, stage: Stage) -> "ProjectState":
        """Forgets `stage` and every stage after it, so the next run redoes them."""
        later = set(STAGE_ORDER[STAGE_ORDER.index(stage) :])
        kept = [done for done in self.completed if done not in later]
        return self.model_copy(update={"completed": kept, "approved": False})


class ProjectStateStore:
    def __init__(self, workspace: ProjectWorkspace) -> None:
        self._workspace = workspace

    def load(self) -> ProjectState:
        path = self._workspace.state_file
        if not path.exists():
            raise ProjectError(
                f"Nao achei um projeto em {self._workspace.root}.",
                "Comece com: talkedit editar caminho/do/video.mp4",
            )
        try:
            return ProjectState.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as error:
            raise ProjectError(
                f"O arquivo {path} esta corrompido.",
                "Apague a pasta do projeto e rode talkedit editar de novo.",
            ) from error

    def exists(self) -> bool:
        return self._workspace.state_file.exists()

    def load_or_create(self, source: Path) -> ProjectState:
        if self.exists():
            return self.load()
        return ProjectState(source=str(source.resolve()))

    def save(self, state: ProjectState) -> None:
        self._workspace.root.mkdir(parents=True, exist_ok=True)
        temporary = self._workspace.state_file.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json(indent=JSON_INDENT), encoding="utf-8")
        temporary.replace(self._workspace.state_file)
