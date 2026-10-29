from dataclasses import dataclass
from pathlib import Path

from talkedit.media import CommandRunner, MediaInfo, ToolPaths
from talkedit.openrouter import CostLedger
from talkedit.pipeline import ProjectContext
from talkedit.plan import CutKind
from talkedit.progress import ProgressReporter
from talkedit.render import (
    AudioSplicer,
    ConcatMuxer,
    Renderer,
    RenderProfile,
    RenderRequest,
    SegmentEncoder,
)
from talkedit.report import ReportMaterial, ReportWriter
from talkedit.resolver import PlanResolver
from talkedit.timeline import FrameGrid, Timeline, TimelineBuilder


@dataclass(frozen=True)
class RenderKit:
    builder: TimelineBuilder
    renderer: Renderer


class RenderKitFactory:
    """Timeline and renderer depend on the frame rate of each video, so they are built
    per project."""

    def __init__(self, runner: CommandRunner, tools: ToolPaths) -> None:
        self._runner = runner
        self._tools = tools

    def for_media(self, media: MediaInfo) -> RenderKit:
        grid = FrameGrid(media.fps)
        renderer = Renderer(
            SegmentEncoder(self._runner, self._tools, grid),
            AudioSplicer(grid),
            ConcatMuxer(self._runner, self._tools),
        )
        return RenderKit(builder=TimelineBuilder(grid), renderer=renderer)


class EditRenderer:
    def __init__(
        self, resolver: PlanResolver, kits: RenderKitFactory, progress: ProgressReporter
    ) -> None:
        self._resolver = resolver
        self._kits = kits
        self._progress = progress

    def timeline(self, context: ProjectContext) -> Timeline:
        cuts = self._resolver.all_cuts(context.plans.load(), context.transcripts.load())
        builder = self._kits.for_media(context.media).builder
        return builder.build(context.media.duration, cuts)

    def render(self, context: ProjectContext, profile: RenderProfile, target: Path) -> None:
        request = RenderRequest(
            source=context.source,
            clean_audio=context.workspace.clean_audio,
            timeline=self.timeline(context),
            work_folder=context.workspace.segments_dir,
            target=target,
        )
        self._kits.for_media(context.media).renderer.render(request, profile, self._progress)


class ProjectReport:
    def __init__(self, resolver: PlanResolver, renderer: EditRenderer, ledger: CostLedger) -> None:
        self._resolver = resolver
        self._renderer = renderer
        self._ledger = ledger

    def material(self, context: ProjectContext) -> ReportMaterial:
        plan = context.plans.load()
        cuts = self._resolver.all_cuts(plan, context.transcripts.load())
        return ReportMaterial(
            plan=plan,
            pauses=[cut for cut in cuts if cut.kind is CutKind.PAUSE],
            original_seconds=context.media.duration,
            edited_seconds=self._renderer.timeline(context).total_seconds(),
            costs=self._ledger.by_function(),
        )


class RenderStep:
    label = "Montando o video final do YouTube"

    def __init__(self, renderer: EditRenderer, report: ProjectReport, writer: ReportWriter) -> None:
        self._renderer = renderer
        self._report = report
        self._writer = writer

    def produce(self, context: ProjectContext) -> None:
        profile = RenderProfile.final(
            context.settings.render.crf, context.settings.render.x264_preset
        )
        self._renderer.render(context, profile, context.workspace.youtube_video)
        markdown = self._writer.markdown(self._report.material(context))
        context.workspace.report_file.write_text(markdown, encoding="utf-8")
