import logging
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from talkedit.audio import AudioCleaner, CleaningChains
from talkedit.editor import AIEditor, Editor, EditorPrompt, FakeEditor
from talkedit.errors import ConfigError
from talkedit.media import CommandRunner, MediaProbe, ToolPaths
from talkedit.openrouter import CostLedger, OpenRouterClient, UrllibTransport
from talkedit.pacing import PaceProfiles, PauseCutter
from talkedit.phrases import PhraseGrouper, PhraseListing
from talkedit.pipeline import (
    CleanAudioStep,
    Pipeline,
    PipelineStep,
    PlanStep,
    PlayerStep,
    ProjectContext,
    ProxyStep,
    ReviewStep,
    TranscribeStep,
)
from talkedit.plan import CutDescriber, TimeLabel
from talkedit.progress import ProgressSink
from talkedit.proxy import PlayerMaker, ProxyMaker
from talkedit.rendering import EditRenderer, ProjectReport, RenderKitFactory, RenderStep
from talkedit.report import PlanSummary, ReportWriter
from talkedit.resolver import LaughterGuard, PlanResolver
from talkedit.reviewer import AIReviewer, EditedScript, FakeReviewer, Reviewer
from talkedit.settings import Settings
from talkedit.settings_loader import (
    DictMerger,
    OverrideParser,
    SettingsLoader,
    SettingsPaths,
    TomlFileReader,
)
from talkedit.settings_writer import ConfigWriter, SettingsStore, TomlValue
from talkedit.stores import PlanStore, TranscriptStore
from talkedit.transcription import (
    AudioChunker,
    FakeTranscriber,
    OpenRouterTranscriber,
    SilenceDetector,
    Transcriber,
    TranscriptionContext,
)
from talkedit.workspace import ProjectStateStore, ProjectWorkspace, RunMode, Stage

API_KEY_VARIABLE = "OPENROUTER_API_KEY"


@dataclass(frozen=True)
class UserHome:
    """~/.talkedit holds what is valid for every video: config, styles and the key."""

    root: Path
    videos: Path

    @classmethod
    def default(cls) -> "UserHome":
        return cls(Path.home() / ".talkedit", Path.home() / "Movies" / "talkedit")

    @property
    def config(self) -> Path:
        return self.root / "config.toml"

    @property
    def key_file(self) -> Path:
        return self.root / "chave_openrouter.txt"

    @property
    def projects_file(self) -> Path:
        return self.root / "projetos.json"

    def settings_paths(self) -> SettingsPaths:
        builtin = Path(__file__).resolve().parent / "estilos"
        return SettingsPaths(self.config, self.root / "estilos", builtin)

    def settings_store(self) -> SettingsStore:
        loader = SettingsLoader(self.settings_paths(), TomlFileReader(), DictMerger())
        return SettingsStore(loader, ConfigWriter(TomlValue()), self.config)


class ApiKeyReader:
    def __init__(self, home: UserHome) -> None:
        self._home = home

    def read(self) -> str:
        from_env = os.environ.get(API_KEY_VARIABLE, "").strip()
        if from_env:
            return from_env
        if self._home.key_file.exists():
            return self._home.key_file.read_text(encoding="utf-8").strip()
        raise ConfigError(
            "Nao achei a chave do OpenRouter.",
            f"Cole a chave no arquivo {self._home.key_file} (uma linha so) e rode de novo.",
        )


@dataclass(frozen=True)
class AIToolkit:
    transcriber: Transcriber
    editor: Editor
    reviewer: Reviewer


@dataclass(frozen=True)
class ToolkitInputs:
    runner: CommandRunner
    tools: ToolPaths
    workspace: ProjectWorkspace
    ledger: CostLedger


class ToolkitFactory(Protocol):
    def toolkit(self, inputs: ToolkitInputs, settings: Settings) -> AIToolkit: ...


class FakeToolkitFactory:
    def toolkit(self, inputs: ToolkitInputs, settings: Settings) -> AIToolkit:
        detector = SilenceDetector(inputs.runner, inputs.tools)
        return AIToolkit(FakeTranscriber(detector), FakeEditor(PhraseGrouper()), FakeReviewer())


class RealToolkitFactory:
    def __init__(self, keys: ApiKeyReader, logger: logging.Logger) -> None:
        self._keys = keys
        self._logger = logger

    def toolkit(self, inputs: ToolkitInputs, settings: Settings) -> AIToolkit:
        client = OpenRouterClient(self._keys.read(), UrllibTransport(self._logger))
        detector = SilenceDetector(inputs.runner, inputs.tools)
        chunker = AudioChunker(inputs.runner, inputs.tools, detector)
        chunk_folder = inputs.workspace.work_dir / "pedacos_audio"
        context = TranscriptionContext(settings, inputs.ledger, chunk_folder)
        grouper, label = PhraseGrouper(), TimeLabel()
        prompt = EditorPrompt(grouper, PhraseListing(label), label)
        script = EditedScript(grouper, CutDescriber(label))
        return AIToolkit(
            OpenRouterTranscriber(client, chunker, context),
            AIEditor(client, prompt, inputs.ledger),
            AIReviewer(client, script, inputs.ledger),
        )


@dataclass(frozen=True)
class ProjectServices:
    pipeline: Pipeline
    renderer: EditRenderer
    report: ProjectReport
    summary: PlanSummary
    describer: CutDescriber


@dataclass(frozen=True)
class SharedParts:
    runner: CommandRunner
    ledger: CostLedger
    progress: ProgressSink
    resolver: PlanResolver


class ProjectAssembler:
    """Composition root: builds every collaborator for one project folder."""

    def __init__(self, tools: ToolPaths, home: UserHome, logger: logging.Logger) -> None:
        self._tools = tools
        self._home = home
        self._logger = logger

    def settings(self, overrides: list[str]) -> Settings:
        merger = DictMerger()
        loader = SettingsLoader(self._home.settings_paths(), TomlFileReader(), merger)
        return loader.load(OverrideParser(merger).parse(overrides))

    def context(
        self, source: Path, workspace: ProjectWorkspace, settings: Settings
    ) -> ProjectContext:
        runner = CommandRunner(workspace.logs_dir, self._logger)
        media = MediaProbe(runner, self._tools).probe(source)
        plans = PlanStore(workspace.plan_file)
        return ProjectContext(
            source, workspace, media, settings, TranscriptStore(workspace.transcript_file), plans
        )

    def services(
        self, context: ProjectContext, mode: RunMode, progress: ProgressSink
    ) -> ProjectServices:
        parts = self._shared(context, progress)
        renderer = EditRenderer(
            parts.resolver, RenderKitFactory(parts.runner, self._tools), parts.progress
        )
        report = ProjectReport(parts.resolver, renderer, parts.ledger)
        label = TimeLabel()
        describer = CutDescriber(label)
        summary = PlanSummary(label)
        steps = self._steps(context, mode, parts)
        steps[Stage.RENDER] = RenderStep(renderer, report, ReportWriter(describer, summary))
        pipeline = Pipeline(steps, ProjectStateStore(context.workspace), parts.progress)
        return ProjectServices(pipeline, renderer, report, summary, describer)

    def _shared(self, context: ProjectContext, progress: ProgressSink) -> SharedParts:
        profile = PaceProfiles().for_pace(context.settings.pace.pace)
        return SharedParts(
            runner=CommandRunner(context.workspace.logs_dir, self._logger),
            ledger=CostLedger.load(context.workspace.costs_file),
            progress=progress,
            resolver=PlanResolver(PauseCutter(profile)),
        )

    def _steps(
        self, context: ProjectContext, mode: RunMode, parts: SharedParts
    ) -> dict[Stage, PipelineStep]:
        inputs = ToolkitInputs(parts.runner, self._tools, context.workspace, parts.ledger)
        toolkit = self._factories()[mode].toolkit(inputs, context.settings)
        chains = CleaningChains(self._tools)
        guard = LaughterGuard()
        return {
            Stage.CLEAN_AUDIO: CleanAudioStep(AudioCleaner(parts.runner, self._tools, chains)),
            Stage.TRANSCRIBE: TranscribeStep(toolkit.transcriber),
            Stage.PROXY: ProxyStep(ProxyMaker(parts.runner, self._tools)),
            Stage.PLAYER: PlayerStep(PlayerMaker(parts.runner, self._tools)),
            Stage.PLAN: PlanStep(toolkit.editor, guard),
            Stage.REVIEW: ReviewStep(toolkit.reviewer, guard),
        }

    def _factories(self) -> MappingProxyType[RunMode, ToolkitFactory]:
        real = RealToolkitFactory(ApiKeyReader(self._home), self._logger)
        return MappingProxyType({RunMode.REAL: real, RunMode.TEST: FakeToolkitFactory()})
