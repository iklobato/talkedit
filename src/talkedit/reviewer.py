from dataclasses import dataclass
from typing import Any, Protocol

from talkedit.openrouter import ChatRequest, CostFunction, CostLedger, OpenRouterClient
from talkedit.phrases import Phrase, PhraseGrouper
from talkedit.plan import Cut, CutDescriber, CutKind, CutSource, CutStatus, EditPlan
from talkedit.schema import StrictSchema
from talkedit.settings import Settings
from talkedit.transcript import Transcript, Word

MARKER = "[corte"

REVIEWER_SYSTEM = """Voce e a revisora de um editor de video. Outra IA ja marcou o que sai
de um video talking head em portugues. Leia como o video vai ficar depois dos cortes e
procure problemas: frase sem sentido, raciocinio quebrado, referencia a algo que foi
cortado, corte arriscado, conteudo importante removido.

Voce pode:
- devolver cortes (restore), pelo id, quando o corte quebra o sentido ou tira algo importante.
- sugerir remover mais (suggest_remove), pelos indices de palavra. E so sugestao: o criador
  decide. Nao sugira cortar piada nem risada.
- escrever observacoes curtas (notes) em portugues simples, para o criador ler.
Na duvida, devolva o corte. Nao comente pausas: o programa cuida delas.
Os trechos cortados aparecem como [corte c3]; a lista dos cortes vem no final."""


@dataclass(frozen=True)
class ReviewMaterial:
    plan: EditPlan
    transcript: Transcript
    settings: Settings


class Reviewer(Protocol):
    def review(self, material: ReviewMaterial) -> EditPlan: ...


class EditedScript:
    """The text as it will sound after the cuts, with a marker where each cut was."""

    def __init__(self, grouper: PhraseGrouper, describer: CutDescriber) -> None:
        self._grouper = grouper
        self._describer = describer

    def render(self, plan: EditPlan, transcript: Transcript) -> str:
        applied = plan.applied()
        lines = [
            self._line(phrase, transcript, applied) for phrase in self._grouper.group(transcript)
        ]
        cuts = "\n".join(f"{cut.id}: {self._describer.describe(cut)}" for cut in applied)
        return "Texto depois dos cortes:\n" + "\n".join(lines) + f"\n\nCortes:\n{cuts}"

    def _line(self, phrase: Phrase, transcript: Transcript, applied: list[Cut]) -> str:
        words = transcript.words[phrase.first : phrase.last + 1]
        tokens = [self._token(word, applied) for word in words]
        kept = [
            token
            for position, token in enumerate(tokens)
            if position == 0 or token != tokens[position - 1] or not token.startswith(MARKER)
        ]
        return f"[w{phrase.first}-w{phrase.last}] " + " ".join(kept)

    def _token(self, word: Word, applied: list[Cut]) -> str:
        owner = next((cut.id for cut in applied if cut.start <= word.middle() <= cut.end), "")
        return f"{MARKER} {owner}]" if owner else word.text


class ReviewerSchema:
    def __init__(self, shapes: StrictSchema) -> None:
        self._shapes = shapes

    def schema(self) -> dict[str, Any]:
        reason = {"reason": {"type": "string"}}
        word_range = {"first_word": {"type": "integer"}, "last_word": {"type": "integer"}}
        return self._shapes.object(
            {
                "restore": self._shapes.array_of({"cut_id": {"type": "string"}, **reason}),
                "suggest_remove": self._shapes.array_of({**word_range, **reason}),
                "notes": {"type": "array", "items": {"type": "string"}},
            }
        )


class ReviewerReply:
    def __init__(self, transcript: Transcript) -> None:
        self._transcript = transcript

    def apply(self, plan: EditPlan, content: dict[str, Any]) -> EditPlan:
        reasons = {item["cut_id"]: item["reason"] for item in content["restore"]}
        cuts = [self._restored(cut, reasons) for cut in plan.cuts]
        suggestions = [
            self._suggestion(len(cuts) + number, item)
            for number, item in enumerate(content["suggest_remove"], 1)
            if 0 <= item["first_word"] <= item["last_word"] < len(self._transcript.words)
        ]
        return plan.replacing([*cuts, *suggestions]).with_notes(list(content["notes"]))

    def _restored(self, cut: Cut, reasons: dict[str, str]) -> Cut:
        if cut.id not in reasons or not cut.is_applied():
            return cut
        return cut.with_status(CutStatus.RESTORED, f"revisora devolveu: {reasons[cut.id]}")

    def _suggestion(self, number: int, item: dict[str, Any]) -> Cut:
        words = self._transcript.words
        return Cut(
            id=f"c{number}",
            start=words[item["first_word"]].start,
            end=words[item["last_word"]].end,
            kind=CutKind.OTHER,
            source=CutSource.REVIEWER,
            status=CutStatus.SUGGESTED,
            text=self._transcript.text_between(item["first_word"], item["last_word"]),
            reason=item["reason"],
        )


class AIReviewer:
    def __init__(self, client: OpenRouterClient, script: EditedScript, ledger: CostLedger) -> None:
        self._client = client
        self._script = script
        self._ledger = ledger

    def review(self, material: ReviewMaterial) -> EditPlan:
        request = ChatRequest(
            model=material.settings.models.reviewer,
            system=REVIEWER_SYSTEM,
            user_parts=[
                {"type": "text", "text": self._script.render(material.plan, material.transcript)}
            ],
            schema_name="revisao_da_edicao",
            schema=ReviewerSchema(StrictSchema()).schema(),
        )
        reply = self._client.chat(request)
        self._ledger.charge(CostFunction.REVIEWER, reply.cost)
        return ReviewerReply(material.transcript).apply(material.plan, reply.content)


class FakeReviewer:
    def review(self, material: ReviewMaterial) -> EditPlan:
        return material.plan.with_notes(["modo de teste: revisora simulada, nada a mudar"])
