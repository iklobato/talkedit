from dataclasses import dataclass

from talkedit.plan import Cut, CutDescriber, CutStatus, EditPlan, TimeLabel


@dataclass(frozen=True)
class ReportMaterial:
    plan: EditPlan
    pauses: list[Cut]
    original_seconds: float
    edited_seconds: float
    costs: dict[str, float]


class PlanSummary:
    def __init__(self, label: TimeLabel) -> None:
        self._label = label

    def line(self, material: ReportMaterial) -> str:
        before = self._label.format(material.original_seconds)
        after = self._label.format(material.edited_seconds)
        count = len(material.plan.applied())
        return f"{before} vai ficar com {after}, {count} trechos removidos"


class ReportWriter:
    """Markdown report: what was cut and why, length before and after, cost."""

    def __init__(self, describer: CutDescriber, summary: PlanSummary) -> None:
        self._describer = describer
        self._summary = summary

    def markdown(self, material: ReportMaterial) -> str:
        plan = material.plan
        sections = [
            "# Relatorio da edicao",
            self._summary.line(material),
            self._pauses(material.pauses),
            self._cuts("Trechos removidos", plan.applied()),
            self._cuts("Trechos devolvidos", self._with_status(plan, CutStatus.RESTORED)),
            self._cuts(
                "Sugestoes da revisora (nao aplicadas)",
                self._with_status(plan, CutStatus.SUGGESTED),
            ),
            self._bullets("Observacoes", plan.notes),
            self._costs(material.costs),
        ]
        return "\n\n".join(section for section in sections if section) + "\n"

    def _with_status(self, plan: EditPlan, status: CutStatus) -> list[Cut]:
        return [cut for cut in plan.cuts if cut.status is status]

    def _pauses(self, pauses: list[Cut]) -> str:
        removed = sum(cut.duration() for cut in pauses)
        return f"Pausas encurtadas: {len(pauses)}, somando {removed:.1f} s."

    def _cuts(self, title: str, cuts: list[Cut]) -> str:
        lines = [self._describer.describe(cut) + self._notes(cut) for cut in cuts]
        return self._bullets(title, lines)

    def _notes(self, cut: Cut) -> str:
        return f" ({'; '.join(cut.notes)})" if cut.notes else ""

    def _bullets(self, title: str, lines: list[str]) -> str:
        if not lines:
            return ""
        return f"## {title}\n\n" + "\n".join(f"- {line}" for line in lines)

    def _costs(self, costs: dict[str, float]) -> str:
        lines = [f"{function}: US$ {usd:.4f}" for function, usd in sorted(costs.items())]
        return self._bullets("Custo", [*lines, f"total: US$ {sum(costs.values()):.4f}"])
