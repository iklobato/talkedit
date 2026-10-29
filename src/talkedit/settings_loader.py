import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from talkedit.errors import ConfigError
from talkedit.settings import Settings

STYLE_KEY = "estilo"
DEFAULT_STYLE = "dinamico"


@dataclass(frozen=True)
class SettingsPaths:
    user_config: Path
    user_styles: Path
    builtin_styles: Path


class DictMerger:
    def merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            merged[key] = self._merge_value(merged.get(key), value)
        return merged

    def _merge_value(self, current: Any, value: Any) -> Any:
        if isinstance(current, dict) and isinstance(value, dict):
            return self.merge(current, value)
        return value


class OverrideParser:
    """Turns `--set ritmo.ritmo=acelerado` into {"ritmo": {"ritmo": "acelerado"}}."""

    def __init__(self, merger: DictMerger) -> None:
        self._merger = merger

    def parse(self, assignments: list[str]) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        for assignment in assignments:
            overrides = self._merger.merge(overrides, self._parse_one(assignment))
        return overrides

    def _parse_one(self, assignment: str) -> dict[str, Any]:
        key, separator, raw_value = assignment.partition("=")
        if not separator or not key.strip():
            raise ConfigError(
                f"Nao entendi a opcao '{assignment}'.",
                "Use o formato secao.opcao=valor, por exemplo ritmo.ritmo=acelerado.",
            )
        nested: Any = self._parse_value(raw_value.strip())
        for part in reversed(key.strip().split(".")):
            nested = {part: nested}
        return nested

    def _parse_value(self, raw_value: str) -> Any:
        try:
            return tomllib.loads(f"value = {raw_value}")["value"]
        except tomllib.TOMLDecodeError:
            return raw_value


class TomlFileReader:
    def read(self, path: Path) -> dict[str, Any]:
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as error:
            raise ConfigError(
                f"O arquivo {path} tem um erro de escrita: {error}.",
                "Abra o arquivo e confira aspas e colchetes na linha indicada.",
            ) from error


class SettingsLoader:
    """Layers, weakest first: built-in style, user config file, one-run overrides."""

    def __init__(self, paths: SettingsPaths, reader: TomlFileReader, merger: DictMerger) -> None:
        self._paths = paths
        self._reader = reader
        self._merger = merger

    def load(self, overrides: dict[str, Any]) -> Settings:
        user = self._read_user_config()
        chosen = self._merger.merge(user, overrides)
        style = self._read_style(str(chosen.get(STYLE_KEY, DEFAULT_STYLE)))
        return self._validate(self._merger.merge(style, chosen))

    def style_defaults(self, name: str) -> Settings:
        """What a style gives with no user config, to tell a user choice from a default."""
        return self._validate({**self._read_style(name), STYLE_KEY: name})

    def validate(self, raw: dict[str, Any]) -> Settings:
        return self._validate(raw)

    def _read_user_config(self) -> dict[str, Any]:
        if not self._paths.user_config.exists():
            return {}
        return self._reader.read(self._paths.user_config)

    def _read_style(self, name: str) -> dict[str, Any]:
        for folder in (self._paths.user_styles, self._paths.builtin_styles):
            candidate = folder / f"{name}.toml"
            if candidate.exists():
                return self._reader.read(candidate)
        raise ConfigError(
            f"Nao achei o estilo '{name}'.",
            f"Use 'dinamico' ou 'natural', ou crie {self._paths.user_styles / name}.toml.",
        )

    def _validate(self, raw: dict[str, Any]) -> Settings:
        try:
            return Settings.model_validate(raw)
        except ValidationError as error:
            raise ConfigError(
                f"Alguma opcao da configuracao esta errada: {error}",
                "Confira o nome e o valor da opcao no config.toml ou no --set.",
            ) from error
