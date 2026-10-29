import tomllib
from pathlib import Path

import pytest
from builders import CutBuilder, TranscriptBuilder

from talkedit.errors import ConfigError, ProjectError
from talkedit.plan import CutKind, CutSource, CutStatus, EditPlan, TimeRange
from talkedit.plan_changes import PlanChanges
from talkedit.projects import ProjectKey, ProjectRegistry
from talkedit.settings import Pace
from talkedit.settings_loader import DictMerger, SettingsLoader, SettingsPaths, TomlFileReader
from talkedit.settings_writer import ConfigWriter, SettingsStore, TomlValue
from talkedit.workspace import ProjectState, ProjectStateStore, ProjectWorkspace

BUILTIN_STYLES = Path(__file__).resolve().parents[1] / "src" / "talkedit" / "estilos"


class StoreFactory:
    def store(self, tmp_path: Path) -> SettingsStore:
        paths = SettingsPaths(tmp_path / "config.toml", tmp_path / "estilos", BUILTIN_STYLES)
        loader = SettingsLoader(paths, TomlFileReader(), DictMerger())
        return SettingsStore(loader, ConfigWriter(TomlValue()), paths.user_config)


class TestSettingsStore:
    WORDS = ["Pix", "talkedit"]
    RULE = 'nunca corte "isso" quando eu mostro um produto'

    def test_saved_defaults_come_back_the_same(self, tmp_path: Path) -> None:
        store = StoreFactory().store(tmp_path)
        chosen = {
            "audio": {"limpeza": "forte"},
            "transcricao": {"palavras_dificeis": self.WORDS},
            "editora": {"regras": [self.RULE]},
        }

        store.save(chosen)

        reloaded = StoreFactory().store(tmp_path).current()
        assert reloaded.audio.intensity.value == "forte"
        assert reloaded.transcription.hard_words == self.WORDS
        assert reloaded.editor.rules == [self.RULE], "quotes inside a rule must survive TOML"

    def test_pace_equal_to_the_style_is_not_written_so_the_style_keeps_control(
        self, tmp_path: Path
    ) -> None:
        store = StoreFactory().store(tmp_path)

        store.save({"estilo": "natural", "ritmo": {"ritmo": "natural"}})

        written = tomllib.loads(store.path.read_text(encoding="utf-8"))
        assert "ritmo" not in written, written
        assert StoreFactory().store(tmp_path).current().pace.pace is Pace.NATURAL

    def test_pace_different_from_the_style_is_written(self, tmp_path: Path) -> None:
        store = StoreFactory().store(tmp_path)

        store.save({"estilo": "natural", "ritmo": {"ritmo": "acelerado"}})

        assert tomllib.loads(store.path.read_text(encoding="utf-8"))["ritmo"] == {
            "ritmo": "acelerado"
        }

    def test_invalid_value_is_refused_and_nothing_is_written(self, tmp_path: Path) -> None:
        store = StoreFactory().store(tmp_path)

        with pytest.raises(ConfigError):
            store.save({"audio": {"limpeza": "maxima"}})

        assert not store.path.exists()

    def test_written_file_explains_each_option_in_portuguese(self, tmp_path: Path) -> None:
        store = StoreFactory().store(tmp_path)

        store.ensure_file()

        assert "# Limpeza da voz:" in store.path.read_text(encoding="utf-8")


class TestPlanChanges:
    WORDS = (("um", 1.0, 1.4), ("dois", 2.0, 2.4), ("tres", 3.0, 3.4))
    DURATION = 5.0
    TAKE = (1.0, 1.4)
    MARK = (1.8, 2.35)
    DOIS_END = 2.4
    SHORT_MARK = (1.0, 1.2)

    def plan(self) -> EditPlan:
        return EditPlan(cuts=[CutBuilder().take("c1", self.TAKE)])

    def test_give_back_then_apply_flips_the_status_with_a_note(self) -> None:
        changes = PlanChanges()

        given = changes.give_back(self.plan(), "c1")
        applied = changes.apply(given, "c1")

        assert given.cuts[0].status is CutStatus.RESTORED
        assert applied.cuts[0].status is CutStatus.APPLIED
        assert applied.cuts[0].notes == ["devolvido por voce", "tirado por voce"]

    def test_marked_span_grows_to_whole_words(self) -> None:
        transcript = TranscriptBuilder().build(self.WORDS, self.DURATION)

        marked = PlanChanges().mark(
            self.plan(), transcript, TimeRange(start=self.MARK[0], end=self.MARK[1])
        )

        cut = marked.cuts[-1]
        assert (cut.start, cut.end, cut.text) == (self.MARK[0], self.DOIS_END, "dois")
        assert (cut.kind, cut.source, cut.id) == (CutKind.MANUAL, CutSource.USER, "u1")

    def test_too_short_mark_is_refused(self) -> None:
        transcript = TranscriptBuilder().build(self.WORDS, self.DURATION)
        span = TimeRange(start=self.SHORT_MARK[0], end=self.SHORT_MARK[1])

        with pytest.raises(ProjectError) as raised:
            PlanChanges().mark(self.plan(), transcript, span)

        assert raised.value.message == "O trecho marcado e curto demais."

    def test_unknown_cut_is_refused(self) -> None:
        with pytest.raises(ProjectError) as raised:
            PlanChanges().apply(self.plan(), "zz")

        assert raised.value.message == "Nao achei o trecho zz."


class TestProjectRegistry:
    def test_newest_first_and_only_folders_with_a_project(self, tmp_path: Path) -> None:
        registry = ProjectRegistry.at(tmp_path / "projetos.json")
        old, new, empty = (ProjectWorkspace(tmp_path / name) for name in ("velho", "novo", "vazio"))
        for workspace in (old, new):
            ProjectStateStore(workspace).save(ProjectState(source="v.mp4"))
        for workspace in (old, empty, new):
            registry.remember(workspace.root)

        listed = [workspace.root.name for workspace in registry.workspaces()]

        assert listed == ["novo", "velho"], listed
        assert registry.find(ProjectKey.of(new.root).value).root == new.root.resolve()
