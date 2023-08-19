import sys
import telnetlib
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from fabric import Connection
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.testbed import ProgrammerProtocol
from shepherd_core.data_models.testbed import TargetPort
from shepherd_core.inventory import Inventory

from . import __version__
from .herd import Herd
from .herd import get_verbose_level
from .herd import logger
from .herd import set_verbose_level

# TODO:
#  - click.command shorthelp can also just be the first sentence of docstring
#  https://click.palletsprojects.com/en/8.1.x/documentation/#command-short-help
#  - document arguments in their docstring (has no help=)
#  - arguments can be configured in a dict and standardized across tools


@click.group(context_settings={"help_option_names": ["-h", "--help"], "obj": {}})
@click.option(
    "--inventory",
    "-i",
    type=click.STRING,
    default="",
    help="List of target hosts as comma-separated string or path to ansible-style yaml file",
)
@click.option(
    "--limit",
    "-l",
    type=click.STRING,
    default="",
    help="Comma-separated list of hosts to limit execution to",
)
@click.option("--user", "-u", type=click.STRING, help="User name for login to nodes")
@click.option(
    "--key-filepath",
    "-k",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
    help="Path to private ssh key file",
)
@click.option("-v", "--verbose", count=True, type=click.INT, default=2)
@click.option(
    "--version",
    is_flag=True,
    help="Prints version-infos (combinable with -v)",
)
@click.pass_context
def cli(
    ctx: click.Context,
    inventory: str,
    limit: str,
    user: Optional[str],
    key_filepath: Optional[Path],
    verbose: int,
    version: bool,
):
    """A primary set of options to configure how to interface the herd"""
    set_verbose_level(verbose)
    if version:
        logger.info("Shepherd-Herd v%s", __version__)
        logger.debug("Python v%s", sys.version)
        logger.debug("Click v%s", click.__version__)
    if not ctx.invoked_subcommand:
        click.echo("Please specify a valid command")

    ctx.obj["herd"] = Herd(inventory, limit, user, key_filepath)


@cli.command(short_help="Power off shepherd nodes")
@click.option("--restart", "-r", is_flag=True, help="Reboot")
@click.pass_context
def poweroff(ctx: click.Context, restart: bool):
    exit_code = ctx.obj["herd"].poweroff(restart)
    sys.exit(exit_code)


@cli.command(short_help="Run COMMAND on the shell")
@click.pass_context
@click.argument("command", type=click.STRING)
@click.option("--sudo", "-s", is_flag=True, help="Run command with sudo")
def shell_cmd(ctx: click.Context, command: str, sudo: bool):
    replies = ctx.obj["herd"].run_cmd(sudo, command)
    ctx.obj["herd"].print_output(replies, 2)  # info-level
    exit_code = max([reply.exited for reply in replies.values()])
    sys.exit(exit_code)


@cli.command(
    short_help="Runs a task or set of tasks with provided config/task file (YAML).",
)
@click.argument(
    "config",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
)
@click.option("--online", "-o", is_flag=True, help="Wait and receive output")
@click.pass_context
def run(ctx: click.Context, config: Path, online: bool):
    if online:
        remote_path = Path("/etc/shepherd/config_for_herd.yaml")
        ctx.obj["herd"].put_file(config, remote_path, force_overwrite=True)
        command = (
            f"shepherd-sheep -{'v' * get_verbose_level()} run {remote_path.as_posix()}"
        )
        replies = ctx.obj["herd"].run_cmd(sudo=True, cmd=command)
        exit_code = max([reply.exited for reply in replies.values()])
        if exit_code:
            logger.error("Programming - Procedure failed - will exit now!")
        ctx.obj["herd"].print_output(replies, 3)  # requires debug level
        sys.exit(exit_code)
    else:
        remote_path = Path("/etc/shepherd/config.yaml")
        ctx.obj["herd"].put_file(config, remote_path, force_overwrite=True)
        exit_code = ctx.obj["herd"].start_measurement()
        logger.info("Shepherd started.")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)


@cli.command(short_help="Record IV data from a harvest-source")
@click.option(
    "--output-path",
    "-o",
    type=click.Path(),
    default=Herd.path_default,
    help="Dir or file path for resulting hdf5 file",
)
@click.option(
    "--virtual-harvester",
    "-a",
    type=click.STRING,
    default="mppt_opt",
    help="Choose one of the predefined virtual harvesters",
)
@click.option(
    "--duration",
    "-d",
    type=click.FLOAT,
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
    for path in ["output_path"]:
        file_path = Path(kwargs[path])
        if not file_path.is_absolute():
            kwargs[path] = Herd.path_default / file_path

    if kwargs.get("virtual_harvester") is not None:
        kwargs["virtual_harvester"] = {"name": kwargs["virtual_harvester"]}

    ts_start = datetime.now().astimezone()
    delay = 0
    if not no_start:
        ts_start, delay = ctx.obj["herd"].find_consensus_time()
        kwargs["time_start"] = ts_start

    task = HarvestTask(**kwargs)
    ctx.obj["herd"].transfer_task(task)

    if not no_start:
        logger.info(
            "Scheduling start of shepherd: %s (in ~ %.2f s)",
            ts_start.isoformat(),
            delay,
        )
        exit_code = ctx.obj["herd"].start_measurement()
        logger.info("Shepherd started.")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)


@cli.command(
    short_help="Emulate data, where INPUT is an hdf5 file on the sheep containing harvesting data",
)
@click.argument(
    "input-path",
    type=click.Path(file_okay=True, dir_okay=False, readable=True),
)
# TODO: switch to local file for input?
@click.option(
    "--output-path",
    "-o",
    type=click.Path(),
    default=Herd.path_default,
    help="Dir or file path for resulting hdf5 file with load recordings",
)
@click.option(
    "--duration",
    "-d",
    type=click.FLOAT,
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
    default="direct",
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
        ts_start, delay = ctx.obj["herd"].find_consensus_time()
        kwargs["time_start"] = ts_start

    task = EmulationTask(**kwargs)
    ctx.obj["herd"].transfer_task(task)

    if not no_start:
        logger.info(
            "Scheduling start of shepherd: %s (in ~ %.2f s)",
            ts_start.isoformat(),
            delay,
        )
        exit_code = ctx.obj["herd"].start_measurement()
        logger.info("Shepherd started.")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)


@cli.command(
    short_help="Start pre-configured shp-service (/etc/shepherd/config.yml, UNSYNCED)",
)
@click.pass_context
def start(ctx: click.Context) -> None:
    if ctx.obj["herd"].check_status():
        logger.info("Shepherd still active, will skip this command!")
        sys.exit(1)
    else:
        exit_code = ctx.obj["herd"].start_measurement()
        logger.info("Shepherd started.")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)


@cli.command(short_help="Information about current state of shepherd measurement")
@click.pass_context
def status(ctx: click.Context) -> None:
    if ctx.obj["herd"].check_status():
        logger.info("Shepherd still active!")
        sys.exit(1)
    else:
        logger.info("Shepherd not active! (measurement is done)")


@cli.command(short_help="Stops any harvest/emulation")
@click.pass_context
def stop(ctx: click.Context) -> None:
    exit_code = ctx.obj["herd"].stop_measurement()
    logger.info("Shepherd stopped.")
    if exit_code > 0:
        logger.debug("-> max exit-code = %d", exit_code)


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
    type=click.Path(),
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
    ctx.obj["herd"].put_file(filename, remote_path, force_overwrite)


@cli.command(short_help="Retrieves remote hdf file FILENAME and stores in in OUTDIR")
@click.argument("filename", type=click.Path())
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

    if force_stop:
        ctx.obj["herd"].stop_measurement()
        if ctx.obj["herd"].await_stop(timeout=30):
            raise Exception("shepherd still active after timeout")

    failed = ctx.obj["herd"].get_file(filename, outdir, timestamp, separate, delete)
    sys.exit(failed)


@cli.command(short_help="Collects information about the hosts")
@click.argument(
    "output-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.pass_context
def inventorize(ctx: click.Context, output_path: Path) -> None:
    file_path = Path("/var/shepherd/inventory.yaml")
    ctx.obj["herd"].run_cmd(
        sudo=True,
        cmd=f"shepherd-sheep inventorize --output_path {file_path.as_posix()}",
    )
    server_inv = Inventory.collect()
    server_inv.to_file(path=Path(output_path) / "inventory_server.yaml", minimal=True)
    failed = ctx.obj["herd"].get_file(
        file_path,
        output_path,
        timestamp=False,
        separate=False,
        delete_src=True,
    )
    # TODO: best case - add all to one file or a new inventories-model?
    sys.exit(failed)


# #############################################################################
#                               OpenOCD Programmer
# #############################################################################


@cli.group(
    short_help="Remote programming/debugging of the target sensor node",
    invoke_without_command=True,
)
@click.option(
    "--port",
    "-p",
    type=click.INT,
    default=4444,
    help="Port on which OpenOCD should listen for telnet",
)
@click.option(
    "--on/--off",
    default=True,
    help="Enable/disable power and debug access to the target",
)
@click.option(
    "--voltage",
    "-v",
    type=click.FLOAT,
    default=3.0,
    help="Target supply voltage",
)
@click.option(
    "--sel_a/--sel_b",
    default=True,
    help="Choose (main)Target that gets connected to virtual Source",
)
@click.pass_context
def target(ctx: click.Context, port: int, on: bool, voltage: float, sel_a: bool):
    # TODO: dirty workaround for deprecated openOCD code
    #   - also no usage of cnx.put, cnx.get, cnx.run, cnx.sudo left
    ctx.obj["openocd_telnet_port"] = port
    sel_target = "sel_a" if sel_a else "sel_b"
    if on or ctx.invoked_subcommand:
        ctx.obj["herd"].run_cmd(
            sudo=True,
            cmd=f"shepherd-sheep -{'v' * get_verbose_level()} "
            f"target-power --on --voltage {voltage} --{sel_target}",
        )
        for cnx in ctx.obj["herd"].group:
            start_openocd(cnx, ctx.obj["herd"].hostnames[cnx.host])
    else:
        replies1 = ctx.obj["herd"].run_cmd(
            sudo=True,
            cmd="systemctl stop shepherd-openocd",
        )
        replies2 = ctx.obj["herd"].run_cmd(
            sudo=True,
            cmd=f"shepherd-sheep -{'v' * get_verbose_level()} target-power --off",
        )
        exit_code = max(
            [reply.exited for reply in replies1.values()]
            + [reply.exited for reply in replies2.values()],
        )
        sys.exit(exit_code)


# @target.result_callback()  # TODO: disabled for now: errors in recent click-versions
@click.pass_context
def process_result(ctx: click.Context, result, **kwargs):  # type: ignore
    if not kwargs["on"]:
        replies1 = ctx.obj["herd"].run_cmd(
            sudo=True,
            cmd="systemctl stop shepherd-openocd",
        )
        replies2 = ctx.obj["herd"].run_cmd(
            sudo=True,
            cmd=f"shepherd-sheep -{'v' * get_verbose_level()} target-power --off",
        )
        exit_code = max(
            [reply.exited for reply in replies1.values()]
            + [reply.exited for reply in replies2.values()],
        )
        sys.exit(exit_code)


def start_openocd(cnx: Connection, hostname: str, timeout: float = 30):
    # TODO: why start a whole telnet-session? we can just flash and verify firmware by remote-cmd
    # TODO: bad design for parallelization, but deprecated anyway
    cnx.sudo("systemctl start shepherd-openocd", hide=True, warn=True)
    ts_end = time.time() + timeout
    while True:
        openocd_status = cnx.sudo(
            "systemctl status shepherd-openocd",
            hide=True,
            warn=True,
        )
        if openocd_status.exited == 0:
            break
        if time.time() > ts_end:
            raise TimeoutError(f"Timed out waiting for openocd on host {hostname}")
        else:
            logger.debug("waiting for openocd on %s", hostname)
            time.sleep(1)


@target.command(short_help="Flashes the binary IMAGE file to the target")
@click.argument(
    "image",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
)
@click.pass_context
def flash(ctx: click.Context, image: Path):
    for cnx in ctx.obj["herd"].group:
        hostname = ctx.obj["herd"].hostnames[cnx.host]
        cnx.put(image, "/tmp/target_image.bin")  # noqa: S108

        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", hostname)
            tn.write(b"program /tmp/target_image.bin verify reset\n")
            res = tn.read_until(b"Verified OK", timeout=5)
            if b"Verified OK" in res:
                logger.info("flashed image on %s successfully", hostname)
            else:
                logger.error("failed flashing image on %s", hostname)


@target.command(short_help="Halts the target")
@click.pass_context
def halt(ctx: click.Context):
    for cnx in ctx.obj["herd"].group:
        hostname = ctx.obj["herd"].hostnames[cnx.host]

        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", hostname)
            tn.write(b"halt\n")
            logger.info("target halted on %s", hostname)


@target.command(short_help="Erases the target")
@click.pass_context
def erase(ctx: click.Context):
    for cnx in ctx.obj["herd"].group:
        hostname = ctx.obj["herd"].hostnames[cnx.host]

        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", hostname)
            tn.write(b"halt\n")
            logger.info("target halted on %s", hostname)
            tn.write(b"nrf52 mass_erase\n")
            logger.info("target erased on %s", hostname)


@target.command(short_help="Resets the target")
@click.pass_context
def reset(ctx: click.Context):
    for cnx in ctx.obj["herd"].group:
        hostname = ctx.obj["herd"].hostnames[cnx.host]
        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", hostname)
            tn.write(b"reset\n")
            logger.info("target reset on %s", hostname)


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
    default=3.0,
    help="Target supply voltage",
)
@click.option(
    "--datarate",
    "-d",
    type=click.INT,
    default=500_000,
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

    ctx.obj["herd"].put_file(kwargs["firmware_file"], tmp_file, force_overwrite=True)
    protocol_dict = {
        "nrf52": ProgrammerProtocol.swd,
        "msp430": ProgrammerProtocol.sbw,
    }
    kwargs["protocol"] = protocol_dict[kwargs["mcu_type"]]
    kwargs["firmware_file"] = Path(tmp_file)
    task = ProgrammingTask(**kwargs)
    ctx.obj["herd"].transfer_task(task, cfg_path)

    command = f"shepherd-sheep -{'v' * get_verbose_level()} run {cfg_path.as_posix()}"
    replies = ctx.obj["herd"].run_cmd(sudo=True, cmd=command)
    exit_code = max([reply.exited for reply in replies.values()])
    if exit_code:
        logger.error("Programming - Procedure failed - will exit now!")
    ctx.obj["herd"].print_output(replies, 3)  # requires debug level
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
