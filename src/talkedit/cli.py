import argparse
import logging
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from talkedit.app import ApiKeyReader, ProjectAssembler, ProjectServices, UserHome
from talkedit.doctor import Doctor, InstallCheck, OpenRouterCheck, ToolsCheck
from talkedit.errors import ConfigError, ProjectError, TalkeditError
from talkedit.media import CommandRunner, ToolPaths
from talkedit.pipeline import ProjectContext
from talkedit.render import RenderProfile
from talkedit.workspace import (
    STAGE_ORDER,
    ProjectState,
    ProjectStateStore,
    ProjectWorkspace,
    RunMode,
    Stage,
)

EXIT_ERROR = 1
EXIT_STOPPED = 130


@dataclass(frozen=True)
class OpenProject:
    state: ProjectState
    context: ProjectContext
    services: ProjectServices


class ProjectOpener:
    """Accepts the video path or the project folder, so every command takes either."""

    def __init__(self, assembler: ProjectAssembler) -> None:
        self._assembler = assembler

    def workspace(self, given: Path) -> ProjectWorkspace:
        if given.is_dir():
            return ProjectWorkspace(given)
        return ProjectWorkspace.beside(given)

    def open(self, workspace: ProjectWorkspace) -> OpenProject:
        state = ProjectStateStore(workspace).load()
        return self.open_state(workspace, state)

    def open_state(self, workspace: ProjectWorkspace, state: ProjectState) -> OpenProject:
        settings = self._assembler.settings(state.overrides)
        context = self._assembler.context(Path(state.source), workspace, settings)
        return OpenProject(state, context, self._assembler.services(context, state.mode))


class PlanPresenter:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def show(self, project: OpenProject) -> None:
        services = project.services
        material = services.report.material(project.context)
        self._logger.info("\n%s\n", services.summary.line(material))
        for cut in material.plan.applied():
            self._logger.info("  %s  %s", cut.id, services.describer.describe(cut))
        for note in material.plan.notes:
            self._logger.info("  obs: %s", note)
        self._logger.info("\nCusto ate agora: US$ %.4f", sum(material.costs.values()))
        folder = shlex.quote(str(project.context.workspace.root))
        self._logger.info("\nProximo passo:")
        self._logger.info("  talkedit previa %s    (previa rapida em baixa qualidade)", folder)
        self._logger.info("  talkedit aprovar %s   (renderiza o video final)", folder)


class CliCommand(Protocol):
    def execute(self, args: argparse.Namespace) -> None: ...


class EditCommand:
    def __init__(self, opener: ProjectOpener, presenter: PlanPresenter) -> None:
        self._opener = opener
        self._presenter = presenter

    def execute(self, args: argparse.Namespace) -> None:
        source = Path(args.video).expanduser().resolve()
        workspace = ProjectWorkspace.beside(source)
        store = ProjectStateStore(workspace)
        if store.exists():
            raise ProjectError(
                f"Este video ja tem um projeto em {workspace.root}.",
                f"Para continuar: talkedit continuar {shlex.quote(str(workspace.root))}",
            )
        mode = RunMode.TEST if args.teste else RunMode.REAL
        state = ProjectState(source=str(source), mode=mode, overrides=args.set)
        store.save(state)
        project = self._opener.open_state(workspace, state)
        project.services.pipeline.run_until(project.context, Stage.REVIEW)
        self._presenter.show(project)


class ContinueCommand:
    def __init__(self, opener: ProjectOpener, presenter: PlanPresenter) -> None:
        self._opener = opener
        self._presenter = presenter

    def execute(self, args: argparse.Namespace) -> None:
        project = self._opener.open(self._opener.workspace(Path(args.pasta).expanduser()))
        last = Stage.RENDER if project.state.approved else Stage.REVIEW
        project.services.pipeline.run_until(project.context, last)
        if not project.state.approved:
            self._presenter.show(project)


class ApproveCommand:
    def __init__(self, opener: ProjectOpener, logger: logging.Logger) -> None:
        self._opener = opener
        self._logger = logger

    def execute(self, args: argparse.Namespace) -> None:
        workspace = self._opener.workspace(Path(args.pasta).expanduser())
        store = ProjectStateStore(workspace)
        state = store.load()
        if not state.is_done(Stage.REVIEW):
            raise ProjectError("O plano ainda nao terminou.", "Rode talkedit continuar antes.")
        store.save(state.approve())
        project = self._opener.open(workspace)
        project.services.pipeline.run_until(project.context, Stage.RENDER)
        self._logger.info("\nPronto. Video: %s", workspace.youtube_video)
        self._logger.info("Relatorio: %s", workspace.report_file)


class PreviewCommand:
    def __init__(self, opener: ProjectOpener, logger: logging.Logger) -> None:
        self._opener = opener
        self._logger = logger

    def execute(self, args: argparse.Namespace) -> None:
        project = self._opener.open(self._opener.workspace(Path(args.pasta).expanduser()))
        target = project.context.workspace.preview_video
        project.services.renderer.render(project.context, RenderProfile.preview(), target)
        self._logger.info("\nPrevia pronta: %s", target)


class RedoCommand:
    def __init__(self, opener: ProjectOpener, presenter: PlanPresenter) -> None:
        self._opener = opener
        self._presenter = presenter

    def execute(self, args: argparse.Namespace) -> None:
        workspace = self._opener.workspace(Path(args.pasta).expanduser())
        store = ProjectStateStore(workspace)
        state = store.load().reopen_from(Stage(args.etapa))
        store.save(state.model_copy(update={"overrides": [*state.overrides, *args.set]}))
        project = self._opener.open(workspace)
        project.services.pipeline.run_until(project.context, Stage.REVIEW)
        self._presenter.show(project)


class VerifyCommand:
    def __init__(self, assembler: ProjectAssembler, home: UserHome, logger: logging.Logger) -> None:
        self._assembler = assembler
        self._home = home
        self._logger = logger

    def execute(self, args: argparse.Namespace) -> None:
        self._logger.info("Verificando a instalacao:")
        runner = CommandRunner(self._home.root / "logs", self._logger)
        settings = self._assembler.settings(args.set)
        checks: list[InstallCheck] = [
            ToolsCheck(runner, ToolPaths.bundled()),
            OpenRouterCheck(ApiKeyReader(self._home), settings),
        ]
        if not Doctor(checks, self._logger).report():
            raise ConfigError("Alguma verificacao falhou.", "Corrija as linhas com ERRO acima.")
        self._logger.info("\nTudo certo.")


class ConfigCommand:
    def __init__(self, home: UserHome, logger: logging.Logger) -> None:
        self._home = home
        self._logger = logger

    def execute(self, args: argparse.Namespace) -> None:
        if not self._home.config.exists():
            self._home.root.mkdir(parents=True, exist_ok=True)
            template = Path(__file__).resolve().parent / "config_modelo.toml"
            shutil.copyfile(template, self._home.config)
        self._logger.info("Sua configuracao: %s", self._home.config)
        self._logger.info("Para editar: open -e %s", shlex.quote(str(self._home.config)))


class ParserFactory:
    PROJECT_HELP = "pasta do projeto ou caminho do video"

    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="talkedit", description="Editor de video com IA.")
        parser.add_argument("--detalhes", action="store_true", help="mostra cada comando rodado")
        commands = parser.add_subparsers(dest="comando", required=True)
        edit = commands.add_parser("editar", help="edita um video bruto e para para voce aprovar")
        edit.add_argument("video", help="caminho do video bruto")
        edit.add_argument("--teste", action="store_true", help="sem IA e sem custo")
        self._add_overrides(edit)
        self._add_project_commands(commands)
        redo = commands.add_parser("refazer", help="refaz uma etapa e as seguintes")
        redo.add_argument("pasta", help=self.PROJECT_HELP)
        redo.add_argument("etapa", choices=[stage.value for stage in STAGE_ORDER[:-1]])
        self._add_overrides(redo)
        self._add_overrides(commands.add_parser("verificar", help="confere instalacao e chave"))
        commands.add_parser("config", help="cria e mostra o arquivo de configuracao")
        return parser

    def _add_project_commands(self, commands: argparse._SubParsersAction) -> None:
        for name, help_text in (
            ("continuar", "retoma um projeto de onde parou"),
            ("aprovar", "aprova o plano e renderiza o video final"),
            ("previa", "gera uma previa rapida em baixa qualidade"),
        ):
            commands.add_parser(name, help=help_text).add_argument("pasta", help=self.PROJECT_HELP)

    def _add_overrides(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--set",
            action="append",
            default=[],
            metavar="SECAO.OPCAO=VALOR",
            help="muda uma opcao so nesta execucao, ex.: ritmo.ritmo=acelerado",
        )


class CommandRegistry:
    def __init__(self, home: UserHome, logger: logging.Logger) -> None:
        self._home = home
        self._logger = logger

    def commands(self) -> MappingProxyType[str, CliCommand]:
        assembler = ProjectAssembler(ToolPaths.bundled(), self._home, self._logger)
        opener = ProjectOpener(assembler)
        presenter = PlanPresenter(self._logger)
        return MappingProxyType(
            {
                "editar": EditCommand(opener, presenter),
                "continuar": ContinueCommand(opener, presenter),
                "aprovar": ApproveCommand(opener, self._logger),
                "previa": PreviewCommand(opener, self._logger),
                "refazer": RedoCommand(opener, presenter),
                "verificar": VerifyCommand(assembler, self._home, self._logger),
                "config": ConfigCommand(self._home, self._logger),
            }
        )


class CommandLine:
    def __init__(self, parser: argparse.ArgumentParser, home: UserHome) -> None:
        self._parser = parser
        self._home = home

    @classmethod
    def entry(cls) -> None:
        sys.exit(cls(ParserFactory().parser(), UserHome.default()).main(sys.argv[1:]))

    def main(self, argv: list[str]) -> int:
        args = self._parser.parse_args(argv)
        logger = self._logger(logging.DEBUG if args.detalhes else logging.INFO)
        try:
            CommandRegistry(self._home, logger).commands()[args.comando].execute(args)
        except TalkeditError as error:
            logger.error("\nErro: %s\nO que fazer: %s", error.message, error.hint)
            return EXIT_ERROR
        except KeyboardInterrupt:
            logger.error(
                "\nParado. O que ja foi feito esta salvo: rode talkedit continuar <pasta>."
            )
            return EXIT_STOPPED
        return 0

    def _logger(self, level: int) -> logging.Logger:
        logger = logging.getLogger("talkedit")
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
        logger.setLevel(level)
        return logger
