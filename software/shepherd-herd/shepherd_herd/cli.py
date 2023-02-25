import sys
import telnetlib
import time
from pathlib import Path

import click
import click_config_file
import yaml

from .herd import Herd
from .herd import logger
from .herd import set_verbose_level

# TODO:
#  - click.command shorthelp can also just be the first sentence of docstring
#  https://click.palletsprojects.com/en/8.1.x/documentation/#command-short-help
#  - document arguments in their docstring (has no help=)
#  - arguments can be configured in a dict and standardized across tools


def yamlprovider(file_path, cmd_name):
    logger.info("reading config from %s, cmd=%s", file_path, cmd_name)
    with open(file_path) as config_data:
        full_config = yaml.safe_load(config_data)
    return full_config


@click.group(context_settings={"help_option_names": ["-h", "--help"], "obj": {}})
@click.option(
    "--inventory",
    "-i",
    type=str,
    default="",
    help="List of target hosts as comma-separated string or path to ansible-style yaml file",
)
@click.option(
    "--limit",
    "-l",
    type=str,
    default="",
    help="Comma-separated list of hosts to limit execution to",
)
@click.option("--user", "-u", type=str, help="User name for login to nodes")
@click.option(
    "--key-filename",
    "-k",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
    help="Path to private ssh key file",
)
@click.option("-v", "--verbose", count=True, default=2)
@click.pass_context
def cli(ctx, inventory, limit, user, key_filename, verbose) -> click.Context:
    """A primary set of options to configure how to interface the herd

    :param ctx:
    :param inventory:
    :param limit:
    :param user:
    :param key_filename:
    :param verbose:
    :return:
    """
    set_verbose_level(verbose)
    ctx.obj["herd"] = Herd(inventory, limit, user, key_filename)
    return ctx  # calm linter


@cli.command(short_help="Power off shepherd nodes")
@click.option("--restart", "-r", is_flag=True, help="Reboot")
@click.pass_context
def poweroff(ctx, restart):
    exit_code = ctx.obj["herd"].poweroff(restart)
    sys.exit(exit_code)


@cli.command(short_help="Run COMMAND on the shell")
@click.pass_context
@click.argument("command", type=str)
@click.option("--sudo", "-s", is_flag=True, help="Run command with sudo")
def run(ctx, command, sudo):
    replies = ctx.obj["herd"].run_cmd(sudo, command)
    for i, hostname in enumerate(ctx.obj["herd"].hostnames.values()):
        click.echo(f"\n************** {hostname} **************")
        click.echo(replies[i].stdout)
        click.echo(f"exit-code = {replies[i].exited}")
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
    type=str,
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
    ctx,
    output_path,
    algorithm,
    duration,
    force_overwrite,
    use_cal_default,
    no_start,
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
    type=str,
    default="A",
    help="Choose Target that gets connected to IO",
)
@click.option(
    "--pwr_target",
    type=str,
    default="A",
    help="Choose (main)Target that gets connected to virtual Source / current-monitor",
)
@click.option(
    "--aux_voltage",
    "-x",
    type=float,
    help="Set Voltage of auxiliary Power Source (second target)",
)
@click.option(
    "--virtsource",
    "-a",  # -v & -s already taken for sheep, so keep it consistent with hrv (algorithm)
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
    ctx,
    input_path,
    output_path,
    duration,
    force_overwrite,
    use_cal_default,
    enable_io,
    io_target,
    pwr_target,
    aux_voltage,
    virtsource,
    no_start,
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
def start(ctx) -> None:
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
def check(ctx) -> None:
    if ctx.obj["herd"].check_state():
        logger.info("Shepherd still active!")
        sys.exit(1)
    else:
        logger.info("Shepherd not active! (measurement is done)")


@cli.command(short_help="Stops any harvest/emulation")
@click.pass_context
def stop(ctx) -> None:
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
    default=Herd.path_default,
    type=click.Path(),
    help="for safety only allowed: /var/shepherd/* or /etc/shepherd/*",
)
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.pass_context
def distribute(ctx, filename, remote_path, force_overwrite):
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
def retrieve(ctx, filename, outdir, timestamp, separate, delete, force_stop) -> None:
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
    type=int,
    default=4444,
    help="Port on which OpenOCD should listen for telnet",
)
@click.option(
    "--on/--off",
    default=True,
    help="Enable/disable power and debug access to the target",
)
@click.option("--voltage", "-v", type=float, default=3.0, help="Target supply voltage")
@click.option(
    "--sel_a/--sel_b",
    default=True,
    help="Choose (main)Target that gets connected to virtual Source",
)
@click.pass_context
def target(ctx, port, on, voltage, sel_a):
    # TODO: dirty workaround for deprecated openOCD code
    #   - also no usage of cnx.put, cnx.get, cnx.run, cnx.sudo left
    ctx.obj["openocd_telnet_port"] = port
    sel_target = "sel_a" if sel_a else "sel_b"
    if on or ctx.invoked_subcommand:
        ctx.obj["herd"].run_cmd(
            sudo=True,
            cmd=f"shepherd-sheep target-power --on --voltage {voltage} --{sel_target}",
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
            cmd="shepherd-sheep target-power --off",
        )
        exit_code = max(
            [reply.exited for reply in replies1.values()]
            + [reply.exited for reply in replies2.values()],
        )
        sys.exit(exit_code)


# @target.result_callback()  # TODO: disabled for now: errors in recent click-versions
@click.pass_context
def process_result(ctx, result, **kwargs):
    if not kwargs["on"]:
        replies1 = ctx.obj["herd"].run_cmd(
            sudo=True,
            cmd="systemctl stop shepherd-openocd",
        )
        replies2 = ctx.obj["herd"].run_cmd(
            sudo=True,
            cmd="shepherd-sheep target-power --off",
        )
        exit_code = max(
            [reply.exited for reply in replies1.values()]
            + [reply.exited for reply in replies2.values()],
        )
        sys.exit(exit_code)


def start_openocd(cnx, hostname, timeout=30):
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
def flash(ctx, image):
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
def halt(ctx):
    for cnx in ctx.obj["herd"].group:
        hostname = ctx.obj["herd"].hostnames[cnx.host]

        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", hostname)
            tn.write(b"halt\n")
            logger.info("target halted on %s", hostname)


@target.command(short_help="Erases the target")
@click.pass_context
def erase(ctx):
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
def reset(ctx):
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
    "--sel_a/--sel_b",
    default=True,
    help="Choose Target-Port for programming",
)
@click.option(
    "--voltage",
    "-v",
    type=click.FLOAT,
    default=3.0,
    help="Target supply voltage",
)
@click.option(
    "--speed",
    "-s",
    type=click.INT,
    default=1_000_000,
    help="Programming-Datarate",
)
@click.option(
    "--target",
    "-t",
    type=click.Choice(["nrf52", "msp430"]),
    default="nrf52",
    help="Target chip",
)
@click.pass_context
def programmer(ctx, firmware_file, sel_a, voltage, speed, target):
    temp_file = "/tmp/target_image.bin"  # noqa: S108
    ctx.obj["herd"].put_file(firmware_file, temp_file, force_overwrite=True)
    command = (
        f"shepherd-sheep programmer {temp_file} --sel_{'a' if sel_a else 'b'} "
        f"-v {voltage} -s {speed} -t {target}"
    )
    replies = ctx.obj["herd"].run_cmd(sudo=True, cmd=command)
    exit_code = max([reply.exited for reply in replies.values()])
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
