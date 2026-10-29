from typing import Any

from builders import CutBuilder, TranscriptBuilder

from talkedit.editor import EditorReply
from talkedit.pacing import PaceProfile, PauseCutter
from talkedit.plan import CutKind, CutStatus, EditPlan, TimeLabel
from talkedit.resolver import LAUGHTER_NOTE, LaughterGuard, PlanResolver
from talkedit.reviewer import ReviewerReply
from talkedit.transcript import Transcript

WORDS = (
    ("entao", 0.0, 0.4),
    ("o", 0.5, 0.6),
    ("primeiro", 0.7, 1.2),
    ("entao", 2.0, 2.4),
    ("o", 2.5, 2.6),
    ("primeiro", 2.7, 3.2),
    ("ponto", 3.3, 3.7),
    ("(risos)", 4.0, 5.0),
)
DURATION = 6.0
FIRST_TAKE = (0.0, 1.2)
FIRST_TAKE_LAST_WORD = 2
SECOND_TAKE_START = 2.0
LAUGH = (4.0, 5.0)
LAST_INDEX = len(WORDS) - 1
VISUAL = (0.55, 0.8)
VISUAL_WORDS = (0.5, 1.2)


class ReplyFactory:
    def transcript(self) -> Transcript:
        return TranscriptBuilder().build(WORDS, DURATION)

    def take(self) -> dict[str, Any]:
        return {
            "first_word": 0,
            "last_word": FIRST_TAKE_LAST_WORD,
            "kind": CutKind.REPEATED_TAKE.value,
            "reason": "mantive a segunda",
        }

    def content(self, removals: list[dict[str, Any]]) -> dict[str, Any]:
        return {"removals": removals, "visual_removals": [], "protected_pauses": [], "emphasis": []}


class TestEditorReply:
    def test_word_range_becomes_a_cut_from_first_word_start_to_last_word_end(self) -> None:
        factory = ReplyFactory()

        plan = EditorReply(factory.transcript(), TimeLabel()).plan(
            factory.content([factory.take()])
        )

        cut = plan.cuts[0]
        assert ((cut.start, cut.end), cut.kind) == (FIRST_TAKE, CutKind.REPEATED_TAKE), cut
        assert cut.text == "entao o primeiro", cut.text

    def test_out_of_range_index_is_kept_in_the_video_with_a_note(self) -> None:
        factory = ReplyFactory()
        broken = {**factory.take(), "last_word": len(WORDS)}

        plan = EditorReply(factory.transcript(), TimeLabel()).plan(factory.content([broken]))

        assert plan.cuts == [], plan.cuts
        assert plan.notes == [
            "a editora indicou 1 trecho(s) com indice de palavra errado; ficaram no video"
        ], plan.notes

    def test_visual_removal_grows_to_whole_words(self) -> None:
        factory = ReplyFactory()
        start, end = VISUAL
        visual = {"start_seconds": start, "end_seconds": end, "reason": "olhou o celular"}
        content = {**factory.content([]), "visual_removals": [visual]}

        plan = EditorReply(factory.transcript(), TimeLabel()).plan(content)

        cut = plan.cuts[0]
        assert (cut.start, cut.end) == VISUAL_WORDS, f"visual cut split a word: {cut}"


class TestLaughterGuard:
    def test_cut_touching_laughter_is_given_back(self) -> None:
        plan = EditPlan(cuts=[CutBuilder().take("c1", LAUGH)])

        guarded = LaughterGuard().protect(plan, ReplyFactory().transcript())

        assert guarded.cuts[0].status is CutStatus.RESTORED, guarded.cuts[0]
        assert guarded.cuts[0].notes == [LAUGHTER_NOTE]

    def test_cut_far_from_laughter_stays_applied(self) -> None:
        plan = EditPlan(cuts=[CutBuilder().take("c1", FIRST_TAKE)])

        guarded = LaughterGuard().protect(plan, ReplyFactory().transcript())

        assert guarded.cuts[0].is_applied(), guarded.cuts[0]


class TestPlanResolver:
    MAX_GAP = 0.3
    LEAD = 0.08
    TAIL = 0.14

    def test_removed_take_leaves_one_pause_not_two_glued_pauses(self) -> None:
        plan = EditPlan(cuts=[CutBuilder().take("c1", FIRST_TAKE)])
        resolver = PlanResolver(PauseCutter(PaceProfile(self.MAX_GAP, self.LEAD, self.TAIL)))

        cuts = resolver.all_cuts(plan, ReplyFactory().transcript())

        first_pause = min((cut for cut in cuts if cut.is_pause()), key=lambda cut: cut.start)
        expected = (0.0, SECOND_TAKE_START - self.LEAD)
        assert (first_pause.start, first_pause.end) == expected, first_pause


class TestReviewerReply:
    def test_restore_gives_cut_back_and_suggestion_is_not_applied(self) -> None:
        plan = EditPlan(cuts=[CutBuilder().take("c1", FIRST_TAKE)])
        content = {
            "restore": [{"cut_id": "c1", "reason": "a frase ficou sem comeco"}],
            "suggest_remove": [{"first_word": LAST_INDEX, "last_word": LAST_INDEX, "reason": "x"}],
            "notes": ["ok"],
        }

        reviewed = ReviewerReply(ReplyFactory().transcript()).apply(plan, content)

        statuses = [(cut.id, cut.status) for cut in reviewed.cuts]
        assert statuses == [("c1", CutStatus.RESTORED), ("c2", CutStatus.SUGGESTED)], statuses
        assert reviewed.notes == ["ok"]
