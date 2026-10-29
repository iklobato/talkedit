from talkedit.plan import Cut, CutKind, CutSource
from talkedit.transcript import TokenKind, Transcript, Word

LANGUAGE = "pt"


class TranscriptBuilder:
    """Words as (text, start, end); text starting with "(" is a sound event."""

    def build(self, spans: tuple[tuple[str, float, float], ...], duration: float) -> Transcript:
        words = [self._word(text, start, end) for text, start, end in spans]
        return Transcript(language=LANGUAGE, duration=duration, words=words)

    def _word(self, text: str, start: float, end: float) -> Word:
        kind = TokenKind.EVENT if text.startswith("(") else TokenKind.WORD
        return Word(text=text, start=start, end=end, kind=kind)


class CutBuilder:
    def pause(self, start: float, end: float) -> Cut:
        return Cut(id="p", start=start, end=end, kind=CutKind.PAUSE, source=CutSource.PACING)

    def take(self, cut_id: str, span: tuple[float, float]) -> Cut:
        start, end = span
        return Cut(
            id=cut_id,
            start=start,
            end=end,
            kind=CutKind.REPEATED_TAKE,
            source=CutSource.EDITOR,
            reason="take repetido",
        )
