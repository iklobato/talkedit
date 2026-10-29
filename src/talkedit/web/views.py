import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar

from talkedit.pipeline import (
    CleanAudioStep,
    PlanStep,
    PlayerStep,
    ProxyStep,
    ReviewStep,
    TranscribeStep,
)
from talkedit.plan import Cut, CutDescriber
from talkedit.projects import OpenProject, ProjectKey
from talkedit.rendering import RenderStep
from talkedit.settings import Settings
from talkedit.web.jobs import JobSnapshot
from talkedit.workspace import STAGE_ORDER, ProjectState, ProjectStateStore, ProjectWorkspace, Stage


class ProjectStatus:
    """One word per project for the list and the page routing."""

    LABELS: ClassVar[MappingProxyType[str, str]] = MappingProxyType(
        {
            "running": "Processando",
            "failed": "Parou com erro",
            "ready": "Pronto",
            "review": "Esperando aprovacao",
            "stopped": "Parado no meio",
        }
    )

    def kind(self, state: ProjectState, job: JobSnapshot, key: str) -> str:
        if job.runs_on(key):
            return "running"
        if job.project_key == key and job.error_message:
            return "failed"
        if state.approved and state.is_done(Stage.RENDER):
            return "ready"
        if state.is_done(Stage.REVIEW):
            return "review"
        return "stopped"

    def label(self, kind: str) -> str:
        return self.LABELS[kind]


class CostReader:
    DIGITS: ClassVar[int] = 4

    def total(self, workspace: ProjectWorkspace) -> float:
        if not workspace.costs_file.exists():
            return 0.0
        spent = json.loads(workspace.costs_file.read_text(encoding="utf-8")).values()
        return self.rounded(sum(spent))

    def rounded(self, usd: float) -> float:
        return round(usd, self.DIGITS)


class StageList:
    LABELS: ClassVar[MappingProxyType[Stage, str]] = MappingProxyType(
        {
            Stage.CLEAN_AUDIO: CleanAudioStep.label,
            Stage.TRANSCRIBE: TranscribeStep.label,
            Stage.PROXY: ProxyStep.label,
            Stage.PLAYER: PlayerStep.label,
            Stage.PLAN: PlanStep.label,
            Stage.REVIEW: ReviewStep.label,
            Stage.RENDER: RenderStep.label,
        }
    )

    def stages(self, state: ProjectState, job: JobSnapshot, key: str) -> list[dict[str, str]]:
        last = Stage.RENDER if state.approved else Stage.REVIEW
        wanted = STAGE_ORDER[: STAGE_ORDER.index(last) + 1]
        active = job if job.runs_on(key) else JobSnapshot()
        return [self._row(stage, state, active) for stage in wanted]

    def _row(self, stage: Stage, state: ProjectState, active: JobSnapshot) -> dict[str, str]:
        """`active` is the job only when it runs on this project, else an empty snapshot."""
        label = self.LABELS[stage]
        running = active.is_running() and active.stage_label == label
        status = "done" if state.is_done(stage) else "running" if running else "waiting"
        return {"id": stage.value, "label": label, "status": status, "detail": active.detail if running else ""}


class ProjectView:
    def __init__(self, status: ProjectStatus, costs: CostReader, stages: StageList) -> None:
        self._status = status
        self._costs = costs
        self._stages = stages

    def row(self, workspace: ProjectWorkspace, job: JobSnapshot) -> dict[str, Any]:
        state = ProjectStateStore(workspace).load()
        key = ProjectKey.of(workspace.root).value
        kind = self._status.kind(state, job, key)
        return {
            "key": key,
            "name": Path(state.source).name,
            "status": kind,
            "statusLabel": self._status.label(kind),
            "cost": self._costs.total(workspace),
            "test": state.mode.value == "teste",
        }

    def detail(self, workspace: ProjectWorkspace, job: JobSnapshot) -> dict[str, Any]:
        state = ProjectStateStore(workspace).load()
        key = ProjectKey.of(workspace.root).value
        return {
            **self.row(workspace, job),
            "folder": str(workspace.root),
            "source": state.source,
            "approved": state.approved,
            "request": state.editor_request,
            "stages": self._stages.stages(state, job, key),
            "hasPlayer": workspace.player_video.exists(),
            "hasPreview": workspace.preview_video.exists(),
            "hasVideo": workspace.youtube_video.exists(),
            "deliveryFolder": str(workspace.delivery_dir),
        }


class PlanView:
    def __init__(self, describer: CutDescriber, costs: CostReader) -> None:
        self._describer = describer
        self._costs = costs

    def plan(self, project: OpenProject) -> dict[str, Any]:
        material = project.services.report.material(project.context)
        pauses = sum(cut.duration() for cut in material.pauses)
        return {
            "summary": project.services.summary.line(material),
            "originalSeconds": material.original_seconds,
            "editedSeconds": material.edited_seconds,
            "removedCount": len(material.plan.applied()),
            "pauseCount": len(material.pauses),
            "pauseSeconds": round(pauses, 1),
            "cuts": [
                self._cut(cut) for cut in sorted(material.plan.cuts, key=lambda cut: cut.start)
            ],
            "notes": material.plan.notes,
            "cost": self._costs.rounded(sum(material.costs.values())),
        }

    def _cut(self, cut: Cut) -> dict[str, Any]:
        return {
            "id": cut.id,
            "start": cut.start,
            "end": cut.end,
            "status": cut.status.value,
            "kind": self._describer.kind_label(cut.kind),
            "source": cut.source.value,
            "text": cut.text,
            "reason": cut.reason,
            "notes": cut.notes,
        }


class SettingsView:
    def view(self, settings: Settings) -> dict[str, Any]:
        return settings.model_dump(by_alias=True, mode="json")
