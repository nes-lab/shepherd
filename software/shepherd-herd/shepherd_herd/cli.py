import sys
import telnetlib
import time
from pathlib import Path
from typing import Optional

import click
import click_config_file
import yaml
from fabric import Connection
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.testbed import ProgrammerProtocol

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


def yamlprovider(file_path: str, cmd_name: str):
    logger.info("reading config from %s, cmd=%s", file_path, cmd_name)
    with open(file_path) as config_data:
        full_config = yaml.safe_load(config_data)
    return full_config


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
def run(ctx: click.Context, command: str, sudo: bool):
    replies = ctx.obj["herd"].run_cmd(sudo, command)
    ctx.obj["herd"].print_output(replies, 2)  # info-level
    exit_code = max([reply.exited for reply in replies.values()])
    sys.exit(exit_code)


@cli.command(short_help="Record IV data from a harvest-source")
@click.option(
    "--output_path",
    "-o",
    type=click.Path(),
    default=Herd.path_default,
    help="Dir or file path for resulting hdf5 file",
)
@click.option(
    "--algorithm",
    "-a",
    type=click.STRING,
    default=None,
    help="Choose one of the predefined virtual harvesters",
)
@click.option(
    "--duration",
    "-d",
    type=click.FLOAT,
    help="Duration of recording in seconds",
)
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option(
    "--use_cal_default",
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
def harvester(
    ctx: click.Context,
    output_path: Path,
    algorithm: Optional[str],
    duration: Optional[float],
    force_overwrite: bool,
    use_cal_default: bool,
    no_start: bool,
):
    fp_output = Path(output_path)
    if not fp_output.is_absolute():
        fp_output = Herd.path_default / output_path

    parameter_dict = {
        "output_path": str(fp_output),
        "harvester": algorithm,
        "duration": duration,
        "force_overwrite": force_overwrite,
        "use_cal_default": use_cal_default,
    }
    parameter_dict = {
        key: val for key, val in parameter_dict.items() if val is not None
    }

    ts_start = delay = 0
    if not no_start:
        ts_start, delay = ctx.obj["herd"].find_consensus_time()
        parameter_dict["start_time"] = ts_start

    ctx.obj["herd"].configure_measurement(
        "harvester",
        parameter_dict,
    )

    if not no_start:
        logger.info("Scheduling start of shepherd at %d (in ~ %.2f s)", ts_start, delay)
        exit_code = ctx.obj["herd"].start_measurement()
        logger.info("Shepherd started.")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)


@cli.command(
    short_help="Emulate data, where INPUT is an hdf5 file containing harvesting data",
)
@click.argument("input_path", type=click.Path())
@click.option(
    "--output_path",
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
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option(
    "--use_cal_default",
    "-c",
    is_flag=True,
    help="Use default calibration values",
)
@click.option(
    "--enable_io/--disable_io",
    default=True,
    help="Switch the GPIO level converter to targets on/off",
)
@click.option(
    "--io_target",
    type=click.Choice(["A", "B"]),
    default="A",
    help="Choose Target that gets connected to IO",
)
@click.option(
    "--pwr_target",
    type=click.Choice(["A", "B"]),
    default="A",
    help="Choose (main)Target that gets connected to virtual Source / current-monitor",
)
@click.option(
    "--aux_voltage",
    "-x",
    type=click.FLOAT,
    help="Set Voltage of auxiliary Power Source (second target)",
)
@click.option(
    "--virtsource",
    "-a",  # -v & -s already taken for sheep, so keep it consistent with hrv (algorithm)
    type=click.STRING,
    default="direct",
    help="Use the desired setting for the virtual source",
)
@click_config_file.configuration_option(provider=yamlprovider, implicit=False)
@click.option(
    "--no-start",
    "-n",
    is_flag=True,
    help="Start shepherd synchronized after uploading config",
)
@click.pass_context
def emulator(
    ctx: click.Context,
    input_path: Path,
    output_path: Path,
    duration: Optional[float],
    force_overwrite: bool,
    use_cal_default: bool,
    enable_io: bool,
    io_target: str,
    pwr_target: str,
    aux_voltage: Optional[float],
    virtsource: str,
    no_start: bool,
):
    fp_input = Path(input_path)
    if not fp_input.is_absolute():
        fp_input = Herd.path_default / input_path

    parameter_dict = {
        "input_path": str(fp_input),
        "force_overwrite": force_overwrite,
        "duration": duration,
        "use_cal_default": use_cal_default,
        "enable_io": enable_io,
        "io_target": io_target,
        "pwr_target": pwr_target,
        "aux_target_voltage": aux_voltage,
        "virtsource": virtsource,
    }
    parameter_dict = {
        key: val for key, val in parameter_dict.items() if val is not None
    }

    if output_path is not None:
        fp_output = Path(output_path)
        if not fp_output.is_absolute():
            fp_output = Herd.path_default / output_path

        parameter_dict["output_path"] = str(fp_output)

    ts_start = delay = 0
    if not no_start:
        ts_start, delay = ctx.obj["herd"].find_consensus_time()
        parameter_dict["start_time"] = ts_start

    ctx.obj["herd"].configure_measurement(
        "emulator",
        parameter_dict,
    )

    if not no_start:
        logger.info("Scheduling start of shepherd at %d (in ~ %.2f s)", ts_start, delay)
        exit_code = ctx.obj["herd"].start_measurement()
        logger.info("Shepherd started.")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)


@cli.command(
    short_help="Start pre-configured shp-service (/etc/shepherd/config.yml, UNSYNCED)",
)
@click.pass_context
def start(ctx: click.Context) -> None:
    if ctx.obj["herd"].check_state():
        logger.info("Shepherd still active, will skip this command!")
        sys.exit(1)
    else:
        exit_code = ctx.obj["herd"].start_measurement()
        logger.info("Shepherd started.")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)


@cli.command(short_help="Information about current shepherd measurement")
@click.pass_context
def check(ctx: click.Context) -> None:
    if ctx.obj["herd"].check_state():
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
    "--remote_path",
    "-r",
    type=click.Path(),
    default=Herd.path_default,
    help="for safety only allowed: /var/shepherd/* or /etc/shepherd/*",
)
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
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
    context_settings={"ignore_unknown_options": True},
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
def program(**kwargs):
    ctx = kwargs.pop("ctx")
    temp_file = "/tmp/target_image.hex"  # noqa: S108

    ctx.obj["herd"].put_file(kwargs["firmware-file"], temp_file, force_overwrite=True)
    protocol_dict = {
        "nrf52": ProgrammerProtocol.swd,
        "msp430": ProgrammerProtocol.sbw,
    }
    kwargs["protocol"] = protocol_dict[kwargs["mcu_type"]]
    cfg = ProgrammingTask(**kwargs)

    command = (
        f"shepherd-sheep -{'v' * get_verbose_level()} program --target-port {cfg.target_port} "
        f"-v {cfg.voltage} -d {cfg.datarate} --mcu-type {cfg.mcu_type} "
        f"--mcu-port {cfg.mcu_port} {'--simulate' if cfg.simulate else ''} "
        f"{temp_file}"
    )
    replies = ctx.obj["herd"].run_cmd(sudo=True, cmd=command)
    exit_code = max([reply.exited for reply in replies.values()])
    if exit_code:
        logger.error("Programming - Procedure failed - will exit now!")
    ctx.obj["herd"].print_output(replies, 3)  # requires debug level
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
