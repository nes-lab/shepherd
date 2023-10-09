import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import shepherd_core
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.testbed import ProgrammerProtocol
from shepherd_core.data_models.testbed import TargetPort

from . import __version__
from .herd import Herd
from .logger import logger as log
from .logger import set_verbosity

# TODO:
#  - click.command shorthelp can also just be the first sentence of docstring
#  https://click.palletsprojects.com/en/8.1.x/documentation/#command-short-help
#  - document arguments in their docstring (has no help=)
#  - arguments can be configured in a dict and standardized across tools


def exit_gracefully(*args) -> None:  # type: ignore
    log.warning("Aborted!")
    sys.exit(0)


@click.group(context_settings={"help_option_names": ["-h", "--help"], "obj": {}})
@click.option(
    "--inventory",
    "-i",
    type=click.STRING,
    default=None,
    help="List of target hosts as comma-separated string or path to ansible-style yaml file",
)
@click.option(
    "--limit",
    "-l",
    type=click.STRING,
    default=None,
    help="Comma-separated list of hosts to limit execution to",
)
@click.option(
    "--user",
    "-u",
    type=click.STRING,
    default=None,
    help="User name for login to nodes",
)
@click.option(
    "--key-filepath",
    "-k",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
    default=None,
    help="Path to private ssh key file",
)
@click.option("--verbose", "-v", is_flag=True)
@click.option(
    "--version",
    is_flag=True,
    help="Prints version-infos (combinable with -v)",
)
@click.pass_context
def cli(
    ctx: click.Context,
    inventory: Optional[str],
    limit: Optional[str],
    user: Optional[str],
    key_filepath: Optional[Path],
    verbose: bool,
    version: bool,
):
    """A primary set of options to configure how to interface the herd"""
    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)

    if verbose:
        set_verbosity()

    if version:
        log.info("Shepherd-Cal v%s", __version__)
        log.debug("Shepherd-Core v%s", shepherd_core.__version__)
        log.debug("Python v%s", sys.version)
        log.debug("Click v%s", click.__version__)

    if not ctx.invoked_subcommand:
        click.echo("Please specify a valid command")

    ctx.obj["herd"] = Herd(inventory, limit, user, key_filepath)


# #############################################################################
#                               Misc-Commands
# #############################################################################


@cli.command(short_help="Power off shepherd nodes")
@click.option("--restart", "-r", is_flag=True, help="Reboot")
@click.pass_context
def poweroff(ctx: click.Context, restart: bool):
    with ctx.obj["herd"] as herd:
        exit_code = herd.poweroff(restart)
    sys.exit(exit_code)


@cli.command(short_help="Run COMMAND on the shell")
@click.pass_context
@click.argument("command", type=click.STRING)
@click.option("--sudo", "-s", is_flag=True, help="Run command with sudo")
def shell_cmd(ctx: click.Context, command: str, sudo: bool):
    with ctx.obj["herd"] as herd:
        replies = herd.run_cmd(sudo=sudo, cmd=command)
        herd.print_output(replies, verbose=True)
        exit_code = max([reply.exited for reply in replies.values()])
    sys.exit(exit_code)


@cli.command(short_help="Collects information about the hosts")
@click.argument(
    "output-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=Path("./"),
)
@click.pass_context
def inventorize(ctx: click.Context, output_path: Path) -> None:
    file_path = Path("/var/shepherd/inventory.yaml")
    with ctx.obj["herd"] as herd:
        herd.run_cmd(
            sudo=True,
            cmd=f"shepherd-sheep inventorize --output_path {file_path.as_posix()}",
        )
        failed = herd.inventorize(output_path)
    sys.exit(failed)


# #############################################################################
#                               Task-Handling
# #############################################################################


@cli.command(
    short_help="Runs a task or set of tasks with provided config/task file (YAML).",
)
@click.argument(
    "config",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
)
@click.option("--attach", "-a", is_flag=True, help="Wait and receive output")
@click.pass_context
def run(ctx: click.Context, config: Path, attach: bool):
    with ctx.obj["herd"] as herd:
        exit_code = herd.run_task(config, attach)
    sys.exit(exit_code)


@cli.command(short_help="Record IV data from a harvest-source")
@click.option(
    "--output-path",
    "-o",
    type=click.Path(dir_okay=True, file_okay=True),
    default=Herd.path_default,
    help="Dir or file path for resulting hdf5 file",
)
@click.option(
    "--virtual-harvester",
    "-a",
    type=click.STRING,
    default=None,
    help="Choose one of the predefined virtual harvesters",
)
@click.option(
    "--duration",
    "-d",
    type=click.FLOAT,
    default=None,
    help="Duration of recording in seconds",
)
@click.option("--force-overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option(
    "--use-cal-default",
    "-c",
    is_flag=True,
    help="Use default calibration values",
)
@click.option(
    "--no-start",
    "-n",
    is_flag=True,
    help="Start shepherd synchronized after uploading config",
)
@click.pass_context
def harvest(
    ctx: click.Context,
    no_start: bool,
    **kwargs,
):
    with ctx.obj["herd"] as herd:
        for path in ["output_path"]:
            file_path = Path(kwargs[path])
            if not file_path.is_absolute():
                kwargs[path] = Herd.path_default / file_path

        if kwargs.get("virtual_harvester") is not None:
            kwargs["virtual_harvester"] = {"name": kwargs["virtual_harvester"]}

        ts_start = datetime.now().astimezone()
        delay = 0
        if not no_start:
            ts_start, delay = herd.find_consensus_time()
            kwargs["time_start"] = ts_start

        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        task = HarvestTask(**kwargs)
        herd.put_task(task)

        if not no_start:
            log.info(
                "Scheduling start of shepherd: %s (in ~ %.2f s)",
                ts_start.isoformat(),
                delay,
            )
            exit_code = herd.start_measurement()
            log.info("Shepherd started.")
            if exit_code > 0:
                log.debug("-> max exit-code = %d", exit_code)


@cli.command(
    short_help="Emulate data, where INPUT is an hdf5 file "
    "on the sheep-host containing harvesting data",
)
@click.argument(
    "input-path",
    type=click.Path(file_okay=True, dir_okay=False),
)
# TODO: switch to local file for input?
@click.option(
    "--output-path",
    "-o",
    type=click.Path(dir_okay=True, file_okay=True),
    default=Herd.path_default,
    help="Dir or file path for resulting hdf5 file with load recordings",
)
@click.option(
    "--duration",
    "-d",
    type=click.FLOAT,
    default=None,
    help="Duration of recording in seconds",
)
@click.option("--force-overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option(
    "--use-cal-default",
    "-c",
    is_flag=True,
    help="Use default calibration values",
)
@click.option(
    "--enable-io/--disable-io",
    default=True,
    help="Switch the GPIO level converter to targets on/off",
)
@click.option(
    "--io-port",
    type=click.Choice(["A", "B"]),
    default="A",
    help="Choose Target that gets connected to IO",
)
@click.option(
    "--pwr-port",
    type=click.Choice(["A", "B"]),
    default="A",
    help="Choose (main)Target that gets connected to virtual Source / current-monitor",
)
@click.option(
    "--voltage-aux",
    "-x",
    type=click.FLOAT,
    default=0.0,
    help="Set Voltage of auxiliary Power Source (second target)",
)
@click.option(
    "--virtual-source",
    "-a",  # -v & -s already taken for sheep, so keep it consistent with hrv (algorithm)
    type=click.STRING,
    default=None,
    help="Use the desired setting for the virtual source",
)
@click.option(
    "--no-start",
    "-n",
    is_flag=True,
    help="Start shepherd synchronized after uploading config",
)
@click.pass_context
def emulate(
    ctx: click.Context,
    no_start: bool,
    **kwargs,
):
    with ctx.obj["herd"] as herd:
        for path in ["input_path", "output_path"]:
            file_path = Path(kwargs[path])
            if not file_path.is_absolute():
                kwargs[path] = Herd.path_default / file_path

        for port in ["io_port", "pwr_port"]:
            kwargs[port] = TargetPort[kwargs[port]]

        if kwargs.get("virtual_source") is not None:
            kwargs["virtual_source"] = {"name": kwargs["virtual_source"]}

        ts_start = datetime.now().astimezone()
        delay = 0
        if not no_start:
            ts_start, delay = herd.find_consensus_time()
            kwargs["time_start"] = ts_start

        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        task = EmulationTask(**kwargs)
        herd.put_task(task)

        if not no_start:
            log.info(
                "Scheduling start of shepherd: %s (in ~ %.2f s)",
                ts_start.isoformat(),
                delay,
            )
            exit_code = herd.start_measurement()
            log.info("Shepherd started.")
            if exit_code > 0:
                log.debug("-> max exit-code = %d", exit_code)


# #############################################################################
#                               Controlling Measurements
# #############################################################################


@cli.command(
    short_help="Start pre-configured shp-service (/etc/shepherd/config.yml, UNSYNCED)",
)
@click.pass_context
def start(ctx: click.Context) -> None:
    ret = 0
    with ctx.obj["herd"] as herd:
        if herd.check_status():
            log.info("Shepherd still active, will skip this command!")
            ret = 1
        else:
            exit_code = herd.start_measurement()
            log.info("Shepherd started.")
            if exit_code > 0:
                log.debug("-> max exit-code = %d", exit_code)
    sys.exit(ret)


@cli.command(short_help="Information about current state of shepherd measurement")
@click.pass_context
def status(ctx: click.Context) -> None:
    ret = 0
    with ctx.obj["herd"] as herd:
        if herd.check_status():
            log.info("Shepherd still active!")
            ret = 1
        else:
            log.info("Shepherd not active! (measurement is done)")
    sys.exit(ret)


@cli.command(short_help="Stops any harvest/emulation")
@click.pass_context
def stop(ctx: click.Context) -> None:
    with ctx.obj["herd"] as herd:
        exit_code = herd.stop_measurement()
    log.info("Shepherd stopped.")
    if exit_code > 0:
        log.debug("-> max exit-code = %d", exit_code)


# #############################################################################
#                               File Handling
# #############################################################################


@cli.command(
    short_help="Uploads a file FILENAME to the remote node, stored in in REMOTE_PATH",
)
@click.argument(
    "filename",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
)
@click.option(
    "--remote-path",
    "-r",
    type=click.Path(file_okay=True, dir_okay=True),
    default=Herd.path_default,
    help="for safety only allowed: /var/shepherd/* or /etc/shepherd/*",
)
@click.option("--force-overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.pass_context
def distribute(
    ctx: click.Context,
    filename: Path,
    remote_path: Path,
    force_overwrite: bool,
):
    with ctx.obj["herd"] as herd:
        herd.put_file(filename, remote_path, force_overwrite)


@cli.command(short_help="Retrieves remote hdf file FILENAME and stores in in OUTDIR")
@click.argument("filename", type=click.Path(file_okay=True, dir_okay=False))
@click.argument(
    "outdir",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
)
@click.option(
    "--timestamp",
    "-t",
    is_flag=True,
    help="Add current timestamp to measurement file",
)
@click.option(
    "--separate",
    "-s",
    is_flag=True,
    help="Every remote node gets own subdirectory",
)
@click.option(
    "--delete",
    "-d",
    is_flag=True,
    help="Delete the file from the remote filesystem after retrieval",
)
@click.option(
    "--force-stop",
    "-f",
    is_flag=True,
    help="Stop the on-going harvest/emulation process before retrieving the data",
)
@click.pass_context
def retrieve(
    ctx: click.Context,
    filename: Path,
    outdir: Path,
    timestamp: bool,
    separate: bool,
    delete: bool,
    force_stop: bool,
) -> None:
    """

    :param ctx: context
    :param filename: remote file with absolute path or relative in '/var/shepherd/recordings/'
    :param outdir: local path to put the files in 'outdir/[node-name]/filename'
    :param timestamp:
    :param separate:
    :param delete:
    :param force_stop:
    """
    with ctx.obj["herd"] as herd:
        if force_stop:
            herd.stop_measurement()
            if herd.await_stop(timeout=30):
                raise Exception("shepherd still active after timeout")

        failed = herd.get_file(filename, outdir, timestamp, separate, delete)
    sys.exit(failed)


# #############################################################################
#                               Pru Programmer
# #############################################################################


@cli.command(
    short_help="Programmer for Target-Controller",
)
@click.argument(
    "firmware-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
)
@click.option(
    "--target-port",
    "-p",
    type=click.Choice(["A", "B"]),
    default="A",
    help="Choose Target-Port of Cape for programming",
)
@click.option(
    "--mcu-port",
    "-m",
    type=click.INT,
    default=1,
    help="Choose MCU on Target-Port (only valid for SBW & SWD)",
)
@click.option(
    "--voltage",
    "-v",
    type=click.FLOAT,
    default=None,
    help="Target supply voltage",
)
@click.option(
    "--datarate",
    "-d",
    type=click.INT,
    default=None,
    help="Bit rate of Programmer (bit/s)",
)
@click.option(
    "--mcu-type",
    "-t",
    type=click.Choice(["nrf52", "msp430"]),
    default="nrf52",
    help="Target MCU",
)
@click.option(
    "--simulate",
    is_flag=True,
    help="dry-run the programmer - no data gets written",
)
@click.pass_context
def program(ctx: click.Context, **kwargs):
    tmp_file = "/tmp/target_image.hex"  # noqa: S108
    cfg_path = Path("/etc/shepherd/config_for_herd.yaml")

    with ctx.obj["herd"] as herd:
        herd.put_file(kwargs["firmware_file"], tmp_file, force_overwrite=True)
        protocol_dict = {
            "nrf52": ProgrammerProtocol.swd,
            "msp430": ProgrammerProtocol.sbw,
        }
        kwargs["protocol"] = protocol_dict[kwargs["mcu_type"]]
        kwargs["firmware_file"] = Path(tmp_file)

        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        task = ProgrammingTask(**kwargs)
        herd.put_task(task, cfg_path)

        command = f"shepherd-sheep --verbose run {cfg_path.as_posix()}"
        replies = herd.run_cmd(sudo=True, cmd=command)
        exit_code = max([reply.exited for reply in replies.values()])
        if exit_code:
            log.error("Programming - Procedure failed - will exit now!")
        herd.print_output(replies, verbose=False)
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
