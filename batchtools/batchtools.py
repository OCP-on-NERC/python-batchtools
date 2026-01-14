import argparse

from .basecommand import Command
from .basecommand import SubParserFactory
from .bj import ListJobsCommand
from .bd import DeleteJobsCommand
from .bl import LogsCommand
from .bp import PrintJobsCommand
from .bq import GpuQueuesCommand
from .br import CreateJobCommand
from .bps import ListPodsCommand


class BatchTools:
    commands: dict[str, type[Command]]
    parser: argparse.ArgumentParser
    subparsers: SubParserFactory

    def __init__(self) -> None:
        self.build_parser()

    def build_parser(self) -> None:
        self.commands = {}
        parser = self.parser = argparse.ArgumentParser(
            description="OpenShift CLI helper"
        )
        self.subparsers = self.parser.add_subparsers(dest="cmd", required=True)

        parser.add_argument(
            "--verbose",
            "-v",
            action="count",
            default=0,
            help="Increase verbosity of output",
        )

        self.register(ListJobsCommand)
        self.register(LogsCommand)
        self.register(DeleteJobsCommand)
        self.register(PrintJobsCommand)
        self.register(GpuQueuesCommand)
        self.register(CreateJobCommand)
        self.register(ListPodsCommand)

    def register(self, handler: type[Command]):
        handler.build_parser(self.subparsers)
        self.commands[handler.name] = handler

    def parse(self, args: list[str] | None = None):
        return self.parser.parse_args(args)

    def run(self, args: list[str] | None = None):
        parsed = self.parse(args)
        self.commands[parsed.cmd].run(parsed)  # pyright: ignore[reportAny]


def main() -> None:
    # if not is_logged_in():
    #     sys.exit(
    #         "You are not logged in to the oc cli. Retrieve the token using 'oc login --web' or retrieving the login token from the openshift UI."
    #     )
    # if not is_on_project():
    #     sys.exit(
    #         "You are not on a project. For metric tracking, you must be on a project. Use oc project <project-name> to get on a project."
    #     )

    app = BatchTools()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
