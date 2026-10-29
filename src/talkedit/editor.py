import base64
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from talkedit.openrouter import ChatRequest, CostFunction, CostLedger, OpenRouterClient
from talkedit.phrases import PhraseGrouper, PhraseListing
from talkedit.plan import Cut, CutKind, CutSource, EditPlan, Emphasis, TimeLabel, TimeRange
from talkedit.schema import StrictSchema
from talkedit.settings import EditorStance, Settings
from talkedit.transcript import Transcript

FAKE_MIN_PHRASES = 2
EDITOR_KINDS = (
    CutKind.REPEATED_TAKE,
    CutKind.ABANDONED,
    CutKind.EDIT_COMMAND,
    CutKind.BEFORE_START,
    CutKind.AFTER_END,
    CutKind.VISUAL,
    CutKind.OTHER,
)


@dataclass(frozen=True)
class EditorMaterial:
    transcript: Transcript
    proxy_video: Path
    settings: Settings


class Editor(Protocol):
    def plan(self, material: EditorMaterial) -> EditPlan: ...


class EditorSchema:
    def __init__(self, shapes: StrictSchema) -> None:
        self._shapes = shapes

    def schema(self) -> dict[str, Any]:
        word_range = {"first_word": {"type": "integer"}, "last_word": {"type": "integer"}}
        kinds = {"type": "string", "enum": [kind.value for kind in EDITOR_KINDS]}
        visual = {"start_seconds": {"type": "number"}, "end_seconds": {"type": "number"}}
        reason = {"reason": {"type": "string"}}
        return self._shapes.object(
            {
                "removals": self._shapes.array_of({**word_range, "kind": kinds, **reason}),
                "visual_removals": self._shapes.array_of({**visual, **reason}),
                "protected_pauses": self._shapes.array_of(
                    {"after_word": {"type": "integer"}, **reason}
                ),
                "emphasis": self._shapes.array_of({**word_range, **reason}),
            }
        )


class EditorPrompt:
    STANCES = MappingProxyType(
        {
            EditorStance.NATURAL: (
                "Postura: conservadora. Corte so erros claros: takes repetidos, frases "
                "abandonadas, comandos para a edicao e a conversa antes e depois. "
                "Nao corte nada so por ritmo."
            ),
            EditorStance.DYNAMIC: (
                "Postura: dinamica, ritmo de YouTube atual. Alem dos erros, pode remover "
                "repeticao de ideia e enrolacao clara que nao faz falta, sempre mantendo o "
                "raciocinio completo."
            ),
        }
    )
    BASE = """Voce e um editor de video profissional de canais brasileiros de YouTube.
O video e um talking head: uma pessoa sozinha falando para a camera, em portugues.
Voce recebe a transcricao com o indice de cada palavra e uma versao leve do video
(1 quadro por segundo, sem som). Marque o que deve sair, como um editor humano faria.

Remova (removals, pelos indices de palavra):
- takes repetidos: quando a pessoa fala a mesma frase ou ideia mais de uma vez, mantenha a
  melhor (normalmente a ultima) e remova as outras.
- frases abandonadas no meio.
- comandos para a edicao, como "corta isso", "de novo", "vou repetir", junto com o take
  que eles anulam.
- conversa antes de comecar e depois de terminar o conteudo.
Remova (visual_removals, pelo tempo em segundos do video): momentos visuais ruins, como
olhar para o lado, tossir, sair do quadro, mexer no celular.

Nunca remova:
- piadas e momentos com risada (eventos de som como "(risos)" aparecem na transcricao).
- pausas dramaticas intencionais: marque em protected_pauses, pela palavra antes da pausa.
- Na duvida, mantenha.

Nao marque pausas comuns: o programa ja encurta as pausas sozinho.
Em emphasis, marque poucas frases fortes para um zoom de enfase, no maximo uma a cada
30 segundos.

Para cada remocao, escreva reason em portugues simples e curto, dizendo por que saiu e, se
for take repetido, qual versao ficou. Exemplo: "take repetido, mantive a versao de 02:32,
mais fluida".
first_word e last_word sao inclusivos e usam o numero do indice (w12 = 12)."""

    def __init__(self, grouper: PhraseGrouper, listing: PhraseListing, label: TimeLabel) -> None:
        self._grouper = grouper
        self._listing = listing
        self._label = label

    def system(self, settings: Settings) -> str:
        parts = [self.BASE, self.STANCES[settings.editor.stance]]
        if settings.editor.rules:
            rules = "\n".join(f"- {rule}" for rule in settings.editor.rules)
            parts.append(f"Regras do criador, siga sempre:\n{rules}")
        if settings.editor.request:
            parts.append(
                "O criador viu o plano anterior e pediu para refazer assim, siga o pedido:\n"
                f"{settings.editor.request}"
            )
        return "\n\n".join(parts)

    def user_text(self, transcript: Transcript) -> str:
        lines = self._listing.lines(self._grouper.group(transcript))
        return f"Duracao do video: {self._label.format(transcript.duration)}.\n\n{lines}"


class EditorReply:
    """Turns the model JSON into cuts. Bad indexes are dropped with a note: when the
    editor is unclear, the take stays."""

    def __init__(self, transcript: Transcript, label: TimeLabel) -> None:
        self._transcript = transcript
        self._label = label

    def plan(self, content: dict[str, Any]) -> EditPlan:
        valid = [item for item in content["removals"] if self._valid(item)]
        cuts = [self._word_cut(item) for item in valid]
        cuts += [self._visual_cut(item) for item in content["visual_removals"]]
        return EditPlan(
            cuts=[
                cut.model_copy(update={"id": f"c{number}"}) for number, cut in enumerate(cuts, 1)
            ],
            emphasis=[self._emphasis(item) for item in content["emphasis"] if self._valid(item)],
            protected=[
                self._pause(item) for item in content["protected_pauses"] if self._inside(item)
            ],
            notes=self._notes(len(content["removals"]) - len(valid)),
        )

    def _notes(self, skipped: int) -> list[str]:
        if not skipped:
            return []
        return [
            f"a editora indicou {skipped} trecho(s) com indice de palavra errado; ficaram no video"
        ]

    def _inside(self, item: dict[str, Any]) -> bool:
        return 0 <= item["after_word"] < len(self._transcript.words) - 1

    def _valid(self, item: dict[str, Any]) -> bool:
        return 0 <= item["first_word"] <= item["last_word"] < len(self._transcript.words)

    def _word_cut(self, item: dict[str, Any]) -> Cut:
        words = self._transcript.words
        return Cut(
            id="",
            start=words[item["first_word"]].start,
            end=words[item["last_word"]].end,
            kind=CutKind(item["kind"]),
            source=CutSource.EDITOR,
            text=self._transcript.text_between(item["first_word"], item["last_word"]),
            reason=item["reason"],
        )

    def _visual_cut(self, item: dict[str, Any]) -> Cut:
        start, end = sorted((float(item["start_seconds"]), float(item["end_seconds"])))
        touched = self._transcript.overlapping(start, end)
        return Cut(
            id="",
            start=min([start, *[word.start for word in touched]]),
            end=max([end, *[word.end for word in touched]]),
            kind=CutKind.VISUAL,
            source=CutSource.EDITOR,
            text=" ".join(word.text for word in touched),
            reason=item["reason"],
        )

    def _emphasis(self, item: dict[str, Any]) -> Emphasis:
        words = self._transcript.words
        start, end = words[item["first_word"]].start, words[item["last_word"]].end
        return Emphasis(start=start, end=end, reason=item["reason"])

    def _pause(self, item: dict[str, Any]) -> TimeRange:
        words = self._transcript.words
        index = item["after_word"]
        return TimeRange(start=words[index].end, end=max(words[index].end, words[index + 1].start))


class AIEditor:
    def __init__(self, client: OpenRouterClient, prompt: EditorPrompt, ledger: CostLedger) -> None:
        self._client = client
        self._prompt = prompt
        self._ledger = ledger

    def plan(self, material: EditorMaterial) -> EditPlan:
        video = base64.b64encode(material.proxy_video.read_bytes()).decode("ascii")
        request = ChatRequest(
            model=material.settings.models.editor,
            system=self._prompt.system(material.settings),
            user_parts=[
                {"type": "text", "text": self._prompt.user_text(material.transcript)},
                {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video}"}},
            ],
            schema_name="plano_de_edicao",
            schema=EditorSchema(StrictSchema()).schema(),
        )
        reply = self._client.chat(request)
        self._ledger.charge(CostFunction.EDITOR, reply.cost)
        return EditorReply(material.transcript, TimeLabel()).plan(reply.content)


class FakeEditor:
    """Test mode: removes the first phrase as talk before the start and marks the
    longest phrase for emphasis. No AI, no cost."""

    def __init__(self, grouper: PhraseGrouper) -> None:
        self._grouper = grouper

    def plan(self, material: EditorMaterial) -> EditPlan:
        phrases = self._grouper.group(material.transcript)
        if len(phrases) < FAKE_MIN_PHRASES:
            return EditPlan(cuts=[], notes=["modo de teste: editora simulada"])
        first = phrases[0]
        longest = max(phrases[1:], key=lambda phrase: phrase.end - phrase.start)
        cut = Cut(
            id="c1",
            start=first.start,
            end=first.end,
            kind=CutKind.BEFORE_START,
            source=CutSource.EDITOR,
            text=first.text,
            reason="modo de teste: a primeira frase sai como conversa antes de comecar",
        )
        emphasis = Emphasis(start=longest.start, end=longest.end, reason="modo de teste")
        return EditPlan(cuts=[cut], emphasis=[emphasis], notes=["modo de teste: editora simulada"])
