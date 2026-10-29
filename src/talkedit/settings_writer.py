import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from talkedit.settings import Settings
from talkedit.settings_loader import SettingsLoader


@dataclass(frozen=True)
class ConfigOption:
    section: str
    key: str
    comment: str


class TomlValue:
    """TOML text for the value types the config uses: text, number, list of text."""

    def render(self, value: Any) -> str:
        if isinstance(value, list):
            return "[" + ", ".join(self.render(item) for item in value) + "]"
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        return repr(value)


class ConfigWriter:
    """Writes ~/.talkedit/config.toml with a plain Portuguese comment above each option.
    The pace is written only when it differs from the chosen style, so changing the
    style later still changes the pace."""

    HEADER: ClassVar[str] = (
        "# Configuracao do talkedit. Vale para todos os videos.\n"
        "# Linhas que comecam com # sao comentarios. A pagina do talkedit (talkedit abrir)\n"
        "# tambem grava este arquivo quando voce clica em 'Salvar padroes'.\n"
        "# Para mudar so numa execucao: talkedit editar video.mp4 --set ritmo.ritmo=acelerado\n"
    )
    OPTIONS: ClassVar[tuple[ConfigOption, ...]] = (
        ConfigOption(
            "",
            "estilo",
            'Estilo pronto: "dinamico" ou "natural" (ou um seu em ~/.talkedit/estilos).',
        ),
        ConfigOption(
            "audio", "limpeza", 'Limpeza da voz: "desligado", "leve", "normal" ou "forte".'
        ),
        ConfigOption(
            "audio", "volume_alvo_lufs", "Volume final. -14 e o padrao do YouTube, Reels e TikTok."
        ),
        ConfigOption("transcricao", "idioma", "Idioma falado no video."),
        ConfigOption(
            "transcricao",
            "palavras_dificeis",
            "Nomes, marcas e termos que a transcricao costuma errar.",
        ),
        ConfigOption("ritmo", "ritmo", 'Ritmo das pausas: "natural", "dinamico" ou "acelerado".'),
        ConfigOption("editora", "regras", "Regras suas para a IA editora, em portugues normal."),
        ConfigOption("modelos", "transcricao", "Modelo de transcricao no OpenRouter."),
        ConfigOption(
            "modelos", "editora", "Modelo da IA editora no OpenRouter (precisa aceitar video)."
        ),
        ConfigOption("modelos", "revisora", "Modelo da IA revisora no OpenRouter (so texto)."),
        ConfigOption(
            "render",
            "qualidade_crf",
            "Qualidade da imagem: 18 fica igual ao original. Numero maior = arquivo menor.",
        ),
        ConfigOption(
            "render", "velocidade_x264", 'Velocidade do render: "fast", "medium" ou "slow".'
        ),
    )

    def __init__(self, values: TomlValue) -> None:
        self._values = values

    def render(self, settings: Settings, style_defaults: Settings) -> str:
        chosen = settings.model_dump(by_alias=True, mode="json")
        from_style = style_defaults.model_dump(by_alias=True, mode="json")
        lines = [self.HEADER]
        current_section = ""
        for option in self.OPTIONS:
            value = self._lookup(chosen, option)
            if option.section == "ritmo" and value == self._lookup(from_style, option):
                continue
            if option.section != current_section:
                lines.append(f"\n[{option.section}]")
                current_section = option.section
            lines.append(f"# {option.comment}\n{option.key} = {self._values.render(value)}")
        return "\n".join(lines) + "\n"

    def write(self, text: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)

    def _lookup(self, dumped: dict[str, Any], option: ConfigOption) -> Any:
        section = dumped[option.section] if option.section else dumped
        return section[option.key]


class SettingsStore:
    """Reads and saves the user's defaults (the "Padroes" page and `talkedit config`)."""

    def __init__(self, loader: SettingsLoader, writer: ConfigWriter, path: Path) -> None:
        self._loader = loader
        self._writer = writer
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def current(self) -> Settings:
        return self._loader.load({})

    def save(self, chosen: dict[str, Any]) -> Settings:
        """`chosen` uses the config file keys (estilo, audio.limpeza, ...); it is validated
        on top of the current file before anything is written."""
        settings = self._loader.load(chosen)
        defaults = self._loader.style_defaults(settings.style)
        self._writer.write(self._writer.render(settings, defaults), self._path)
        return settings

    def ensure_file(self) -> None:
        if not self._path.exists():
            self.save({})
