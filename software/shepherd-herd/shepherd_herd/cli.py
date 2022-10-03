import logging
import sys
import telnetlib
import time
from pathlib import Path

import click
import click_config_file
import yaml

from .sheep_control import assemble_context
from .sheep_control import check_sheep
from .sheep_control import configure_sheep
from .sheep_control import find_consensus_time
from .sheep_control import logger
from .sheep_control import poweroff_sheep
from .sheep_control import start_sheep
from .sheep_control import stop_sheep

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
    type=click.Path(exists=True),
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
    ctx = assemble_context(ctx, inventory, limit, user, key_filename, verbose)
    return ctx  # calm linter


@cli.command(short_help="Power off shepherd nodes")
@click.option("--restart", "-r", is_flag=True, help="Reboot")
@click.pass_context
def poweroff(ctx, restart):
    poweroff_sheep(ctx.obj["fab group"], ctx.obj["hostnames"], restart)


@cli.command(short_help="Run COMMAND on the shell")
@click.pass_context
@click.argument("command", type=str)
@click.option("--sudo", "-s", is_flag=True, help="Run command with sudo")
def run(ctx, command, sudo):
    for cnx in ctx.obj["fab group"]:
        click.echo(f"\n************** {ctx.obj['hostnames'][cnx.host]} **************")
        if sudo:
            cnx.sudo(command, warn=True)
        else:
            cnx.run(command, warn=True)


@cli.command(short_help="Record IV data from a harvest-source")
@click.option(
    "--output_path",
    "-o",
    type=click.Path(),
    default="/var/shepherd/recordings/",
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
    "--duration", "-d", type=click.FLOAT, help="Duration of recording in seconds"
)
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option(
    "--use_cal_default", "-c", is_flag=True, help="Use default calibration values"
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
        fp_output = Path("/var/shepherd/recordings") / output_path

    parameter_dict = {
        "output_path": str(fp_output),
        "harvester": algorithm,
        "duration": duration,
        "force_overwrite": force_overwrite,
        "use_cal_default": use_cal_default,
    }

    if not no_start:
        ts_start, delay = find_consensus_time(ctx.obj["fab group"])
        parameter_dict["start_time"] = ts_start

    configure_sheep(
        ctx.obj["fab group"],
        "harvester",
        parameter_dict,
        ctx.obj["hostnames"],
        ctx.obj["verbose"],
    )

    if not no_start:
        logger.debug(
            "Scheduling start of shepherd at %d (in ~ %.2f s)", ts_start, delay
        )
        start_sheep(ctx.obj["fab group"], ctx.obj["hostnames"])


@cli.command(
    short_help="Emulate data, where INPUT is an hdf5 file containing harvesting data"
)
@click.argument("input_path", type=click.Path())
@click.option(
    "--output_path",
    "-o",
    type=click.Path(),
    default="/var/shepherd/recordings/",
    help="Dir or file path for resulting hdf5 file with load recordings",
)
@click.option(
    "--duration", "-d", type=click.FLOAT, help="Duration of recording in seconds"
)
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option(
    "--use_cal_default", "-c", is_flag=True, help="Use default calibration values"
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
        fp_input = Path("/var/shepherd/recordings") / input_path

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
            fp_output = Path("/var/shepherd/recordings") / output_path

        parameter_dict["output_path"] = str(fp_output)

    if not no_start:
        ts_start, delay = find_consensus_time(ctx.obj["fab group"])
        parameter_dict["start_time"] = ts_start

    configure_sheep(
        ctx.obj["fab group"],
        "emulator",
        parameter_dict,
        ctx.obj["hostnames"],
        ctx.obj["verbose"],
    )

    if not no_start:
        logger.debug(
            "Scheduling start of shepherd at %d (in ~ %.2f s)", ts_start, delay
        )
        start_sheep(ctx.obj["fab group"], ctx.obj["hostnames"])


@cli.command(
    short_help="Start pre-configured shp-service (/etc/shepherd/config.yml, UNSYNCED)"
)
@click.pass_context
def start(ctx) -> None:
    if check_sheep(ctx.obj["fab group"], ctx.obj["hostnames"]):
        logger.info("Shepherd still running, will skip this command!")
        sys.exit(1)
    else:
        start_sheep(ctx.obj["fab group"], ctx.obj["hostnames"])
        logger.info("Shepherd started.")


@cli.command(short_help="Information about current shepherd measurement")
@click.pass_context
def check(ctx) -> None:
    ret = check_sheep(ctx.obj["fab group"], ctx.obj["hostnames"])
    if ret:
        logger.info("Shepherd still running!")
        sys.exit(1)
    else:
        logger.info("Shepherd not running! (measurement is done)")


@cli.command(short_help="Stops any harvest/emulation")
@click.pass_context
def stop(ctx) -> None:
    stop_sheep(ctx.obj["fab group"], ctx.obj["hostnames"])
    logger.info("Shepherd stopped.")


@cli.command(
    short_help="Uploads a file FILENAME to the remote node, stored in in REMOTE_PATH"
)
@click.argument(
    "filename",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
)
@click.option(
    "--remote_path",
    "-r",
    default="/var/shepherd/recordings/",
    type=click.Path(),
    help="for safety only allowed: /var/shepherd/* or /etc/shepherd/*",
)
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.pass_context
def distribute(ctx, filename, remote_path, force_overwrite):

    filename = Path(filename).absolute()
    logger.info("Local source path = %s", filename)

    remotes_allowed = [
        Path("/var/shepherd/recordings/"),  # default
        Path("/var/shepherd/"),
        Path("/etc/shepherd/"),
    ]
    if remote_path is None:
        remote_path = remotes_allowed[0]
        logger.info("Remote path not provided -> default = %s", remote_path)
    else:
        remote_path = Path(remote_path).absolute()
        path_allowed = False
        for remote_allowed in remotes_allowed:
            if str(remote_allowed).startswith(str(remote_path)):
                path_allowed = True
        if path_allowed:
            logger.info("Remote path = %s", remote_path)
        else:
            raise NameError(f"provided path was forbidden ('{remote_path}')")

    tmp_path = Path("/tmp") / filename.name  # noqa: S108
    xtr_arg = "-f" if force_overwrite else "-n"

    for cnx in ctx.obj["fab group"]:
        cnx.put(str(filename), str(tmp_path))  # noqa: S108
        cnx.sudo(f"mv {xtr_arg} {tmp_path} {remote_path}")


@cli.command(short_help="Retrieves remote hdf file FILENAME and stores in in OUTDIR")
@click.argument("filename", type=click.Path())
@click.argument(
    "outdir",
    type=click.Path(
        exists=True,
    ),
)
@click.option(
    "--timestamp", "-t", is_flag=True, help="Add current timestamp to measurement file"
)
@click.option(
    "--separate", "-s", is_flag=True, help="Every remote node gets own subdirectory"
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
    :return:
    """
    time_str = time.strftime("%Y_%m_%dT%H_%M_%S")
    xtra_ts = f"_{ time_str }" if timestamp else ""
    failed_retrieval = False

    if force_stop:
        stop_sheep(ctx.obj["fab group"], ctx.obj["hostnames"])
        ts_end = time.time() + 30
        while check_sheep(ctx.obj["fab group"], ctx.obj["hostnames"]):
            if time.time() > ts_end:
                logger.setLevel(logging.DEBUG)
                # change lvl so check_shepherd tells about troubled node
                check_sheep(ctx.obj["fab group"], ctx.obj["hostnames"])
                raise Exception("shepherd still active after timeout")
            time.sleep(1)

    for cnx in ctx.obj["fab group"]:
        if separate:
            target_path = Path(outdir) / ctx.obj["hostnames"][cnx.host]
            xtra_node = ""
        else:
            target_path = Path(outdir)
            xtra_node = f"_{ctx.obj['hostnames'][cnx.host]}"

        if Path(filename).is_absolute():
            filepath = Path(filename)
        else:
            filepath = Path("/var/shepherd/recordings") / filename

        res = cnx.run(
            f"test -f {filepath}",
            hide=True,
            warn=True,
        )
        if res.exited > 0:
            logger.error(
                "remote file '%s' does not exist on node %s",
                filepath,
                ctx.obj["hostnames"][cnx.host],
            )
            failed_retrieval = True
            continue

        if not target_path.exists():
            logger.info("creating local dir %s", target_path)
            target_path.mkdir()

        local_path = target_path / (
            str(filepath.stem) + xtra_ts + xtra_node + filepath.suffix
        )

        logger.info(
            "retrieving remote file '%s' from %s to local '%s'",
            filepath,
            ctx.obj["hostnames"][cnx.host],
            local_path,
        )
        cnx.get(str(filepath), local=str(local_path))
        if delete:
            logger.info(
                "deleting %s from remote %s",
                filepath,
                ctx.obj["hostnames"][cnx.host],
            )
            cnx.sudo(f"rm {filepath}", hide=True)

    sys.exit(failed_retrieval)


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
    ctx.obj["openocd_telnet_port"] = port
    sel_target = "sel_a" if sel_a else "sel_b"
    if on or ctx.invoked_subcommand:
        for cnx in ctx.obj["fab group"]:
            cnx.sudo(
                f"shepherd-sheep target-power --on --voltage {voltage} --{sel_target}",
                hide=True,
            )
            start_openocd(cnx, ctx.obj["hostnames"][cnx.host])
    else:
        for cnx in ctx.obj["fab group"]:
            cnx.sudo("systemctl stop shepherd-openocd")
            cnx.sudo("shepherd-sheep target-power --off", hide=True)


# @target.result_callback()  # TODO: disabled for now: errors in recent click-versions
@click.pass_context
def process_result(ctx, result, **kwargs):
    if not kwargs["on"]:
        for cnx in ctx.obj["fab group"]:
            cnx.sudo("systemctl stop shepherd-openocd")
            cnx.sudo("shepherd-sheep target-power --off", hide=True)


def start_openocd(cnx, hostname, timeout=30):
    # TODO: why start a whole telnet-session? we can just flash and verify firmware by remote-cmd
    cnx.sudo("systemctl start shepherd-openocd", hide=True, warn=True)
    ts_end = time.time() + timeout
    while True:
        openocd_status = cnx.sudo(
            "systemctl status shepherd-openocd", hide=True, warn=True
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
    "image", type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True)
)
@click.pass_context
def flash(ctx, image):
    for cnx in ctx.obj["fab group"]:
        cnx.put(image, "/tmp/target_image.bin")  # noqa: S108

        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", ctx.obj["hostnames"][cnx.host])
            tn.write(b"program /tmp/target_image.bin verify reset\n")
            res = tn.read_until(b"Verified OK", timeout=5)
            if b"Verified OK" in res:
                logger.info(
                    "flashed image on %s successfully", ctx.obj["hostnames"][cnx.host]
                )
            else:
                logger.error(
                    "failed flashing image on %s", ctx.obj["hostnames"][cnx.host]
                )


@target.command(short_help="Halts the target")
@click.pass_context
def halt(ctx):
    for cnx in ctx.obj["fab group"]:

        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", ctx.obj["hostnames"][cnx.host])
            tn.write(b"halt\n")
            logger.info("target halted on %s", ctx.obj["hostnames"][cnx.host])


@target.command(short_help="Erases the target")
@click.pass_context
def erase(ctx):
    for cnx in ctx.obj["fab group"]:

        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", ctx.obj["hostnames"][cnx.host])
            tn.write(b"halt\n")
            logger.info("target halted on %s", ctx.obj["hostnames"][cnx.host])
            tn.write(b"nrf52 mass_erase\n")
            logger.info("target erased on %s", ctx.obj["hostnames"][cnx.host])


@target.command(short_help="Resets the target")
@click.pass_context
def reset(ctx):
    for cnx in ctx.obj["fab group"]:

        with telnetlib.Telnet(cnx.host, ctx.obj["openocd_telnet_port"]) as tn:
            logger.debug("connected to openocd on %s", ctx.obj["hostnames"][cnx.host])
            tn.write(b"reset\n")
            logger.info("target reset on %s", ctx.obj["hostnames"][cnx.host])


# #############################################################################
#                               Pru Programmer
# #############################################################################

if __name__ == "__main__":
    cli()
