from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AudioIntensity(Enum):
    OFF = "desligado"
    LIGHT = "leve"
    NORMAL = "normal"
    STRONG = "forte"


class Pace(Enum):
    NATURAL = "natural"
    DYNAMIC = "dinamico"
    FAST = "acelerado"


class EditorStance(Enum):
    """How much the AI editor is allowed to cut beyond clear mistakes."""

    NATURAL = "natural"
    DYNAMIC = "dinamico"


class SettingsSection(BaseModel):
    """Config keys are Portuguese aliases because the user edits the file by hand."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)


class AudioSettings(SettingsSection):
    intensity: AudioIntensity = Field(AudioIntensity.NORMAL, alias="limpeza")
    target_lufs: float = Field(-14.0, alias="volume_alvo_lufs", ge=-24.0, le=-9.0)


class TranscriptionSettings(SettingsSection):
    language: str = Field("pt", alias="idioma", min_length=2, max_length=3)
    hard_words: list[str] = Field(default_factory=list, alias="palavras_dificeis")


class PaceSettings(SettingsSection):
    pace: Pace = Field(Pace.DYNAMIC, alias="ritmo")


class EditorSettings(SettingsSection):
    stance: EditorStance = Field(EditorStance.DYNAMIC, alias="postura")
    rules: list[str] = Field(default_factory=list, alias="regras")
    request: str = Field("", alias="pedido", max_length=2000)

    def with_request(self, request: str) -> "EditorSettings":
        """The creator's ask for one redo of the plan ("cortando demais, seja conservador")."""
        return self.model_copy(update={"request": request})


class ModelSettings(SettingsSection):
    transcriber: str = Field("elevenlabs/scribe-v2", alias="transcricao")
    editor: str = Field("google/gemini-4-argon", alias="editora")
    reviewer: str = Field("google/gemini-3.5-flash-lite", alias="revisora")


class RenderSettings(SettingsSection):
    crf: int = Field(18, alias="qualidade_crf", ge=0, le=51)
    x264_preset: str = Field("medium", alias="velocidade_x264")


class Settings(SettingsSection):
    style: str = Field("dinamico", alias="estilo")
    audio: AudioSettings = Field(AudioSettings(), alias="audio")
    transcription: TranscriptionSettings = Field(TranscriptionSettings(), alias="transcricao")
    pace: PaceSettings = Field(PaceSettings(), alias="ritmo")
    editor: EditorSettings = Field(EditorSettings(), alias="editora")
    models: ModelSettings = Field(ModelSettings(), alias="modelos")
    render: RenderSettings = Field(RenderSettings(), alias="render")

    def with_editor_request(self, request: str) -> "Settings":
        return self.model_copy(update={"editor": self.editor.with_request(request)})
