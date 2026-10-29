import argparse
import logging
import os
import shlex
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from talkedit.app import ApiKeyReader, ProjectAssembler, UserHome
from talkedit.doctor import Doctor, InstallCheck, OpenRouterCheck, ToolsCheck
from talkedit.drive import DriveDownloader, DriveLinkParser, UrllibFetcher, VideoSource
from talkedit.errors import ConfigError, ProjectError, TalkeditError
from talkedit.media import CommandRunner, ToolPaths
from talkedit.progress import ProgressReporter
from talkedit.projects import OpenProject, ProjectOpener, ProjectRegistry
from talkedit.settings_writer import SettingsStore
from talkedit.web.actions import FinderOpener
from talkedit.web.server import ServerOptions, WebServerBuilder
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
    def __init__(
        self, opener: ProjectOpener, presenter: PlanPresenter, sources: VideoSource
    ) -> None:
        self._opener = opener
        self._presenter = presenter
        self._sources = sources

    def execute(self, args: argparse.Namespace) -> None:
        chosen = Path(args.pasta).expanduser() if args.pasta else None
        source = self._sources.local_path(args.video, chosen)
        workspace = ProjectWorkspace.beside(source)
        store = ProjectStateStore(workspace)
        if store.exists():
            raise ProjectError(
                f"Este video ja tem um projeto em {workspace.root}.",
                f"Para continuar: talkedit continuar {shlex.quote(str(workspace.root))}",
            )
        mode = RunMode.TEST if args.teste else RunMode.REAL
        state = ProjectState(source=str(source), mode=mode, overrides=args.set)
        project = self._opener.open_state(workspace, state)
        store.save(state)
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


class OpenCommand:
    """`talkedit abrir`: the local page. Stops with Ctrl+C; a running job stops with it
    and `talkedit continuar` (or the page, opened again) resumes it."""

    def __init__(self, builder: WebServerBuilder, logger: logging.Logger) -> None:
        self._builder = builder
        self._logger = logger

    def execute(self, args: argparse.Namespace) -> None:
        running = self._builder.build(ServerOptions(args.porta, FinderOpener()))
        self._logger.info("talkedit aberto em: %s", running.address)
        self._logger.info("Para fechar: Ctrl+C neste Terminal.")
        if not args.sem_navegador:
            os.system(f"open {shlex.quote(running.address)} > /dev/null 2>&1")
        try:
            running.server.serve_forever()
        finally:
            running.server.server_close()


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
    def __init__(self, store: SettingsStore, logger: logging.Logger) -> None:
        self._store = store
        self._logger = logger

    def execute(self, args: argparse.Namespace) -> None:
        self._store.ensure_file()
        self._logger.info("Sua configuracao: %s", self._store.path)
        self._logger.info("Para editar: open -e %s", shlex.quote(str(self._store.path)))


class ParserFactory:
    PROJECT_HELP = "pasta do projeto ou caminho do video"

    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="talkedit", description="Editor de video com IA.")
        parser.add_argument("--detalhes", action="store_true", help="mostra cada comando rodado")
        commands = parser.add_subparsers(dest="comando", required=True)
        self._add_edit_command(commands)
        self._add_project_commands(commands)
        redo = commands.add_parser("refazer", help="refaz uma etapa e as seguintes")
        redo.add_argument("pasta", help=self.PROJECT_HELP)
        redo.add_argument("etapa", choices=[stage.value for stage in STAGE_ORDER[:-1]])
        self._add_overrides(redo)
        self._add_overrides(commands.add_parser("verificar", help="confere instalacao e chave"))
        commands.add_parser("config", help="cria e mostra o arquivo de configuracao")
        page = commands.add_parser("abrir", help="abre a pagina do talkedit no navegador")
        page.add_argument("--porta", type=int, default=0, help="porta local (padrao: uma livre)")
        page.add_argument("--sem-navegador", action="store_true", help="so mostra o endereco")
        return parser

    def _add_edit_command(self, commands: argparse._SubParsersAction) -> None:
        edit = commands.add_parser("editar", help="edita um video bruto e para para voce aprovar")
        edit.add_argument("video", help="caminho do video bruto ou link publico do Google Drive")
        edit.add_argument(
            "--pasta",
            help="onde salvar o video baixado do Google Drive (padrao: ~/Movies/talkedit)",
        )
        edit.add_argument("--teste", action="store_true", help="sem IA e sem custo")
        self._add_overrides(edit)

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
        registry = ProjectRegistry.at(self._home.projects_file)
        opener = ProjectOpener(assembler, ProgressReporter.create(self._logger), registry)
        presenter = PlanPresenter(self._logger)
        return MappingProxyType(
            {
                "editar": EditCommand(opener, presenter, self._video_source()),
                "continuar": ContinueCommand(opener, presenter),
                "aprovar": ApproveCommand(opener, self._logger),
                "previa": PreviewCommand(opener, self._logger),
                "refazer": RedoCommand(opener, presenter),
                "verificar": VerifyCommand(assembler, self._home, self._logger),
                "config": ConfigCommand(self._home.settings_store(), self._logger),
                "abrir": OpenCommand(
                    WebServerBuilder(self._home, self._video_source(), self._logger), self._logger
                ),
            }
        )

    def _video_source(self) -> VideoSource:
        parser = DriveLinkParser()
        downloader = DriveDownloader(UrllibFetcher(self._logger), parser, self._logger)
        return VideoSource(parser, downloader, self._home.videos)


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
