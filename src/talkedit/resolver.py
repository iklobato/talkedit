from talkedit.pacing import PauseCutter
from talkedit.plan import Cut, CutStatus, EditPlan
from talkedit.transcript import Transcript, Word

LAUGHTER_NOTE = "tinha risada no trecho; a ferramenta nunca corta risada"


class LaughterGuard:
    """Hard rule from the spec: a cut that touches laughter is given back, whoever asked."""

    def protect(self, plan: EditPlan, transcript: Transcript) -> EditPlan:
        laughs = [word for word in transcript.words if word.is_laughter()]
        return plan.replacing([self._checked(cut, laughs) for cut in plan.cuts])

    def _checked(self, cut: Cut, laughs: list[Word]) -> Cut:
        touches = any(cut.overlaps(laugh.start, laugh.end) for laugh in laughs)
        if cut.is_applied() and touches:
            return cut.with_status(CutStatus.RESTORED, LAUGHTER_NOTE)
        return cut


class PlanResolver:
    """Pauses are not stored in the plan. They are cut again on the words that remain,
    so a removed take never leaves two short pauses glued into one long one."""

    def __init__(self, cutter: PauseCutter) -> None:
        self._cutter = cutter

    def kept_transcript(self, plan: EditPlan, transcript: Transcript) -> Transcript:
        applied = plan.applied()
        kept = [word for word in transcript.words if not self._removed(word, applied)]
        return transcript.model_copy(update={"words": kept})

    def all_cuts(self, plan: EditPlan, transcript: Transcript) -> list[Cut]:
        pauses = self._cutter.cuts(self.kept_transcript(plan, transcript), plan.protected)
        return [*plan.applied(), *pauses]

    def _removed(self, word: Word, applied: list[Cut]) -> bool:
        return any(cut.start <= word.middle() <= cut.end for cut in applied)
