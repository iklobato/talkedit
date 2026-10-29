from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from talkedit.audio import AudioCleaner
from talkedit.editor import Editor, EditorMaterial
from talkedit.errors import ProjectError
from talkedit.media import MediaInfo
from talkedit.progress import ProgressReporter
from talkedit.proxy import ProxyMaker
from talkedit.resolver import LaughterGuard
from talkedit.reviewer import Reviewer, ReviewMaterial
from talkedit.settings import Settings
from talkedit.stores import PlanStore, TranscriptStore
from talkedit.transcription import Transcriber
from talkedit.workspace import STAGE_ORDER, ProjectState, ProjectStateStore, ProjectWorkspace, Stage


@dataclass(frozen=True)
class ProjectContext:
    source: Path
    workspace: ProjectWorkspace
    media: MediaInfo
    settings: Settings
    transcripts: TranscriptStore
    plans: PlanStore


class PipelineStep(Protocol):
    label: str

    def produce(self, context: ProjectContext) -> None: ...


class CleanAudioStep:
    label = "Limpando o audio"

    def __init__(self, cleaner: AudioCleaner) -> None:
        self._cleaner = cleaner

    def produce(self, context: ProjectContext) -> None:
        if not context.media.has_audio:
            raise ProjectError("O video nao tem som.", "Use um video com a sua voz gravada.")
        context.workspace.work_dir.mkdir(parents=True, exist_ok=True)
        self._cleaner.clean(context.source, context.workspace.clean_audio, context.settings.audio)


class TranscribeStep:
    label = "Transcrevendo a fala"

    def __init__(self, transcriber: Transcriber) -> None:
        self._transcriber = transcriber

    def produce(self, context: ProjectContext) -> None:
        audio = context.workspace.clean_audio
        context.transcripts.save(self._transcriber.transcribe(audio, context.media.duration))


class ProxyStep:
    label = "Fazendo a copia leve do video para a IA"

    def __init__(self, maker: ProxyMaker) -> None:
        self._maker = maker

    def produce(self, context: ProjectContext) -> None:
        self._maker.make(context.source, context.workspace.proxy_video)


class PlanStep:
    label = "IA editora escolhendo o que sai"

    def __init__(self, editor: Editor, guard: LaughterGuard) -> None:
        self._editor = editor
        self._guard = guard

    def produce(self, context: ProjectContext) -> None:
        transcript = context.transcripts.load()
        material = EditorMaterial(transcript, context.workspace.proxy_video, context.settings)
        context.plans.save(self._guard.protect(self._editor.plan(material), transcript))


class ReviewStep:
    label = "IA revisora conferindo a edicao"

    def __init__(self, reviewer: Reviewer, guard: LaughterGuard) -> None:
        self._reviewer = reviewer
        self._guard = guard

    def produce(self, context: ProjectContext) -> None:
        transcript = context.transcripts.load()
        material = ReviewMaterial(context.plans.load(), transcript, context.settings)
        context.plans.save(self._guard.protect(self._reviewer.review(material), transcript))


class Pipeline:
    """Runs the steps in order and saves progress after each one, so a closed terminal
    or an error resumes where it stopped."""

    def __init__(
        self,
        steps: dict[Stage, PipelineStep],
        store: ProjectStateStore,
        progress: ProgressReporter,
    ) -> None:
        self._steps = steps
        self._store = store
        self._progress = progress

    def run_until(self, context: ProjectContext, last: Stage) -> ProjectState:
        state = self._store.load_or_create(context.source)
        wanted = STAGE_ORDER[: STAGE_ORDER.index(last) + 1]
        pending = [stage for stage in wanted if not state.is_done(stage)]
        for number, stage in enumerate(pending, 1):
            self._progress.stage(f"{number}/{len(pending)}", self._steps[stage].label)
            self._steps[stage].produce(context)
            state = state.mark_done(stage)
            self._store.save(state)
        return state
