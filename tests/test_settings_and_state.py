from pathlib import Path

import pytest

from talkedit.errors import ConfigError
from talkedit.settings import EditorStance, Pace
from talkedit.settings_loader import (
    DictMerger,
    OverrideParser,
    SettingsLoader,
    SettingsPaths,
    TomlFileReader,
)
from talkedit.workspace import ProjectState, Stage

BUILTIN_STYLES = Path(__file__).resolve().parents[1] / "src" / "talkedit" / "estilos"


class LoaderFactory:
    def loader(self, tmp_path: Path) -> SettingsLoader:
        paths = SettingsPaths(tmp_path / "config.toml", tmp_path / "estilos", BUILTIN_STYLES)
        return SettingsLoader(paths, TomlFileReader(), DictMerger())


class TestSettingsLoader:
    def test_without_config_the_dynamic_style_is_used(self, tmp_path: Path) -> None:
        settings = LoaderFactory().loader(tmp_path).load({})

        assert (settings.pace.pace, settings.editor.stance) == (Pace.DYNAMIC, EditorStance.DYNAMIC)

    def test_natural_style_changes_pace_and_editor_stance(self, tmp_path: Path) -> None:
        settings = LoaderFactory().loader(tmp_path).load({"estilo": "natural"})

        assert (settings.pace.pace, settings.editor.stance) == (Pace.NATURAL, EditorStance.NATURAL)

    def test_one_run_override_beats_config_file_and_style(self, tmp_path: Path) -> None:
        (tmp_path / "config.toml").write_text('[ritmo]\nritmo = "natural"\n', encoding="utf-8")
        overrides = OverrideParser(DictMerger()).parse(["ritmo.ritmo=acelerado"])

        settings = LoaderFactory().loader(tmp_path).load(overrides)

        assert settings.pace.pace is Pace.FAST

    def test_unknown_style_says_which_styles_exist(self, tmp_path: Path) -> None:
        loader = LoaderFactory().loader(tmp_path)

        with pytest.raises(ConfigError) as raised:
            loader.load({"estilo": "cinema"})

        assert raised.value.message == "Nao achei o estilo 'cinema'."
        assert raised.value.hint.startswith("Use 'dinamico' ou 'natural'"), raised.value.hint

    def test_misspelled_option_value_is_rejected(self, tmp_path: Path) -> None:
        overrides = OverrideParser(DictMerger()).parse(["audio.limpeza=maxima"])

        with pytest.raises(ConfigError) as raised:
            LoaderFactory().loader(tmp_path).load(overrides)

        assert "limpeza" in raised.value.message, raised.value.message


class TestOverrideParser:
    def test_assignment_without_equals_explains_the_format(self) -> None:
        with pytest.raises(ConfigError) as raised:
            OverrideParser(DictMerger()).parse(["ritmo.ritmo"])

        assert raised.value.hint == (
            "Use o formato secao.opcao=valor, por exemplo ritmo.ritmo=acelerado."
        )


class TestProjectState:
    def test_redo_forgets_the_stage_and_every_later_one(self) -> None:
        state = ProjectState(source="v.mp4", completed=list(Stage), approved=True)

        reopened = state.reopen_from(Stage.PLAN)

        assert reopened.completed == [Stage.CLEAN_AUDIO, Stage.TRANSCRIBE, Stage.PROXY, Stage.PLAYER]
        assert not reopened.approved, "a redone plan needs a new approval"
