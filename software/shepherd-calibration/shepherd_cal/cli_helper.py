import signal
import sys
from types import FrameType

import typer

from .logger import activate_verbosity
from .logger import log


def exit_gracefully(_signum: int, _frame: FrameType | None) -> None:
    log.warning("Exiting!")
    sys.exit(0)


def cli_setup_callback(*, verbose: bool = False, print_version: bool = False) -> None:
    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)

    if verbose:
        activate_verbosity()

    if print_version:
        from importlib import metadata

        log.debug("Python v%s", sys.version)
        log.info("Sync-Analysis v%s", metadata.version("sync-analysis"))
        log.info("Shepherd-Core v%s", metadata.version("shepherd-core"))
        log.info("Typer v%s", metadata.version("typer"))
        log.info("Click v%s", metadata.version("click"))


# NOTE: typer.Option seems to imply Optional[type]
host_arg_t = typer.Argument(default=..., help="Name or IP of host-sheep")
user_opt_t = typer.Option(default="jane", help="Username for Host")
pass_opt_t = typer.Option(
    default=None,
    help="Password for User - only needed when key-credentials are missing",
)

smu_ip_opt_t = typer.Option(default="192.168.1.108", help="IP of SMU-Device in network")
smu_2w_opt_t = typer.Option(
    False,
    "--smu-2wire/--smu-4wire",
    is_flag=True,
    help="DON'T use 4wire-mode for measuring voltage (NOT recommended)",
)
smu_nc_opt_t = typer.Option(
    default=16,
    help="measurement duration in pwrline cycles (.001 to 25, but > 18 can cause error-msgs)",
)
verbose_opt_t = typer.Option(
    False,
    "--verbose",
    "-v",
    is_flag=True,
    help="Activate debug- instead of info-level",
)

ofile_opt_t = typer.Option(
    default=None,
    dir_okay=False,
    file_okay=True,
    exists=False,
    help="save-file, will be generic with timestamp if not provided",
)
ifile_opt_t = typer.Option(
    default=None,
    dir_okay=False,
    file_okay=True,
    exists=True,
    help="Input-YAML, wrapped data-model",
)

hrv_opt_t = typer.Option(
    False,
    "--harvester-only",
    "-h",
    is_flag=True,
    help="only handle harvester",
)
emu_opt_t = typer.Option(
    False,
    "--emulator-only",
    "-e",
    is_flag=True,
    help="only handle emulator",
)
