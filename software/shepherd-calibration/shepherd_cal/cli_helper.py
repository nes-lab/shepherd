import signal
import sys

import click
import shepherd_core
import typer

from . import __version__
from .logger import activate_verbose
from .logger import logger


def exit_gracefully(*args):  # type: ignore
    logger.warning("Aborted!")
    sys.exit(0)


def cli_setup_callback(verbose: bool = False, print_version: bool = False) -> None:
    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)

    if verbose:
        activate_verbose()

    if print_version:
        logger.info("Shepherd-Cal v%s", __version__)
        logger.debug("Shepherd-Core v%s", shepherd_core.__version__)
        logger.debug("Python v%s", sys.version)
        logger.debug("Typer v%s", typer.__version__)
        logger.debug("Click v%s", click.__version__)


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
    exists=True,
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
    False, "--harvester-only", "-h", is_flag=True, help="only handle harvester"
)
emu_opt_t = typer.Option(
    False, "--emulator-only", "-e", is_flag=True, help="only handle emulator"
)
