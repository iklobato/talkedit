from dataclasses import dataclass
from typing import ClassVar

from talkedit.errors import ProjectError
from talkedit.plan import Cut, CutKind, CutSource, CutStatus, EditPlan, TimeRange
from talkedit.transcript import Transcript


@dataclass(frozen=True)
class CutDecision:
    status: CutStatus
    note: str


class PlanChanges:
    """What the creator changes on the review page. The AI's laughter guard does not
    apply here: a cut the creator asks for is the creator's call."""

    MIN_MANUAL_SECONDS: ClassVar[float] = 0.5
    MANUAL_PREFIX: ClassVar[str] = "u"
    GIVE_BACK: ClassVar[CutDecision] = CutDecision(CutStatus.RESTORED, "devolvido por voce")
    APPLY: ClassVar[CutDecision] = CutDecision(CutStatus.APPLIED, "tirado por voce")

    def give_back(self, plan: EditPlan, cut_id: str) -> EditPlan:
        return self._decide(plan, cut_id, self.GIVE_BACK)

    def apply(self, plan: EditPlan, cut_id: str) -> EditPlan:
        return self._decide(plan, cut_id, self.APPLY)

    def mark(self, plan: EditPlan, transcript: Transcript, span: TimeRange) -> EditPlan:
        if span.end - span.start < self.MIN_MANUAL_SECONDS:
            raise ProjectError(
                "O trecho marcado e curto demais.",
                "Arraste na linha do tempo por pelo menos meio segundo.",
            )
        touched = transcript.overlapping(span.start, span.end)
        cut = Cut(
            id=f"{self.MANUAL_PREFIX}{self._next_number(plan)}",
            start=min([span.start, *[word.start for word in touched]]),
            end=max([span.end, *[word.end for word in touched]]),
            kind=CutKind.MANUAL,
            source=CutSource.USER,
            text=" ".join(word.text for word in touched),
            reason="marcado por voce na linha do tempo",
        )
        return plan.replacing([*plan.cuts, cut])

    def _decide(self, plan: EditPlan, cut_id: str, decision: CutDecision) -> EditPlan:
        if cut_id not in {cut.id for cut in plan.cuts}:
            raise ProjectError(f"Nao achei o trecho {cut_id}.", "Recarregue a pagina.")
        cuts = [
            cut.with_status(decision.status, decision.note) if cut.id == cut_id else cut
            for cut in plan.cuts
        ]
        return plan.replacing(cuts)

    def _next_number(self, plan: EditPlan) -> int:
        manual = [cut.id for cut in plan.cuts if cut.id.startswith(self.MANUAL_PREFIX)]
        return len(manual) + 1
