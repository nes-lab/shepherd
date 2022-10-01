"""
shepherd_herd
~~~~~
click-based command line utility for controlling a group of shepherd nodes
remotely through ssh. Provides commands for starting/stopping harvester and
emulator, retrieving recordings to the local machine and flashing firmware
images to target sensor nodes.

:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""

import contextlib
import logging
import sys
import telnetlib
import time
from io import StringIO
from pathlib import Path
from typing import List

import click
import click_config_file
import numpy as np
import yaml
from fabric import Group

__version__ = "0.4.0"

consoleHandler = logging.StreamHandler()
logger = logging.getLogger("shepherd-herd")
logger.addHandler(consoleHandler)

# TODO:
#  - click.command shorthelp can also just be the first sentence of docstring
#  https://click.palletsprojects.com/en/8.1.x/documentation/#command-short-help
#  - document arguments in their docstring (has no help=)
#  - arguments can be configured in a dict and standardized across tools


def yamlprovider(file_path, cmd_name):
    logger.info("reading config from %s", file_path)
    with open(file_path) as config_data:
        full_config = yaml.safe_load(config_data)
    return full_config


def find_consensus_time(group):
    """Finds a start time in the future when all nodes should start service

    In order to run synchronously, all nodes should start at the same time.
    This is achieved by querying all nodes to check any large time offset,
    agreeing on a common time in the future and waiting for that time on each
    node.

    Args:
        group (fabric.Group): Group of fabric hosts on which to start shepherd.
    """
    # Get the current time on each target node
    ts_nows = np.empty(len(group))
    for i, cnx in enumerate(group):
        res = cnx.run("date +%s", hide=True, warn=True)
        ts_nows[i] = float(res.stdout)

    if len(ts_nows) == 1:
        ts_start = ts_nows[0] + 20
    else:
        ts_max = max(ts_nows)
        # Check for excessive time difference among nodes
        ts_diffs = ts_nows - ts_max
        if any(abs(ts_diffs) > 10):
            raise Exception("Time difference between hosts greater 10s")

        # We need to estimate a future point in time such that all nodes are ready
        ts_start = ts_max + 20 + 2 * len(group)
    return int(ts_start), float(ts_start - ts_nows[0])


def configure_shepherd(
    group: Group,
    mode: str,
    parameters: dict,
    hostnames: dict,
    verbose: int = 0,
):
    """Configures shepherd service on the group of hosts.

    Rolls out a configuration file according to the given command and parameters
    service.

    Args:
        group (fabric.Group): Group of fabric hosts on which to start shepherd.
        mode (str): What shepherd is supposed to do. One of 'harvester' or 'emulator'.
        parameters (dict): Parameters for shepherd-sheep
        hostnames (dict): Dictionary of hostnames corresponding to fabric hosts
        verbose (int): Verbosity for shepherd-sheep
    """
    config_dict = {
        "mode": mode,
        "verbose": verbose,
        "parameters": parameters,
    }
    config_yml = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

    logger.debug("Rolling out the following config:\n\n%s", config_yml)

    for cnx in group:
        res = cnx.sudo("systemctl status shepherd", hide=True, warn=True)
        if res.exited != 3:
            raise Exception(f"shepherd not inactive on {hostnames[cnx.host]}")

        cnx.put(StringIO(config_yml), "/tmp/config.yml")  # noqa: S108
        cnx.sudo("mv /tmp/config.yml /etc/shepherd/config.yml")


def start_shepherd(
    group: Group,
    hostnames: dict,
):
    """Starts shepherd service on the group of hosts.

    Args:
        group (fabric.Group): Group of fabric hosts on which to start shepherd.
        hostnames (dict): Dictionary of hostnames corresponding to fabric hosts
    """
    for cnx in group:
        res = cnx.sudo("systemctl status shepherd", hide=True, warn=True)
        if res.exited != 3:
            raise Exception(f"shepherd not inactive on {hostnames[cnx.host]}")
        res = cnx.sudo("systemctl start shepherd", hide=True, warn=True)


def check_shepherd(group: Group, hostnames: dict) -> bool:
    """Returns true ss long as one instance is still measuring

    :param group:
    :param hostnames:
    :return: True is one node is still running
    """
    running = False
    for cnx in group:
        res = cnx.sudo("systemctl status shepherd", hide=True, warn=True)
        if res.exited != 3:
            running = True
            logger.info("shepherd still active on %s", hostnames[cnx.host])
    return running


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
def cli(ctx, inventory, limit, user, key_filename, verbose) -> None:
    """A primary set of options to configure how to interface the herd

    :param ctx:
    :param inventory:
    :param limit:
    :param user:
    :param key_filename:
    :param verbose:
    :return:
    """
    if limit.rstrip().endswith(","):
        limit = limit.split(",")[:-1]
    else:
        limit = None

    if inventory.rstrip().endswith(","):
        hostlist = inventory.split(",")[:-1]
        if limit is not None:
            hostlist = list(set(hostlist) & set(limit))
        hostnames = {hostname: hostname for hostname in hostlist}

    else:
        # look at all these directories for inventory-file
        if inventory == "":
            inventories = [
                "/etc/shepherd/herd.yml",
                "~/herd.yml",
                "inventory/herd.yml",
            ]
        else:
            inventories = [inventory]
        host_path = None
        for inventory in inventories:
            if Path(inventory).exists():
                host_path = Path(inventory)

        if host_path is None:
            raise click.FileError(", ".join(inventories))

        with open(host_path) as stream:
            try:
                inventory_data = yaml.safe_load(stream)
            except yaml.YAMLError:
                raise click.UsageError(f"Couldn't read inventory file {host_path}")

        hostlist = []
        hostnames = {}
        for hostname, hostvars in inventory_data["sheep"]["hosts"].items():
            if isinstance(limit, List) and (hostname not in limit):
                continue

            if "ansible_host" in hostvars:
                hostlist.append(hostvars["ansible_host"])
                hostnames[hostvars["ansible_host"]] = hostname
            else:
                hostlist.append(hostname)
                hostnames[hostname] = hostname

        if user is None:
            with contextlib.suppress(KeyError):
                user = inventory_data["sheep"]["vars"]["ansible_user"]

    if user is None:
        raise click.UsageError("Provide user by command line or in inventory file")

    if len(hostlist) < 1 or len(hostnames) < 1:
        raise click.UsageError(
            "Provide remote hosts (either inventory empty or limit does not match)"
        )

    if verbose == 0:
        logger.setLevel(logging.ERROR)
    elif verbose == 1:
        logger.setLevel(logging.WARNING)
    elif verbose == 2:
        logger.setLevel(logging.INFO)
    elif verbose > 2:
        logger.setLevel(logging.DEBUG)

    ctx.obj["verbose"] = verbose

    connect_kwargs = {}
    if key_filename is not None:
        connect_kwargs["key_filename"] = key_filename

    ctx.obj["fab group"] = Group(*hostlist, user=user, connect_kwargs=connect_kwargs)
    ctx.obj["hostnames"] = hostnames


@cli.command(short_help="Power off shepherd nodes")
@click.option("--restart", "-r", is_flag=True, help="Reboot")
@click.pass_context
def poweroff(ctx, restart):
    for cnx in ctx.obj["fab group"]:
        if restart:
            logger.info("rebooting %s", ctx.obj["hostnames"][cnx.host])
            cnx.sudo("reboot", hide=True, warn=True)
        else:
            logger.info("powering off %s", ctx.obj["hostnames"][cnx.host])
            cnx.sudo("poweroff", hide=True, warn=True)


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


@target.result_callback()
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
@click.argument("image", type=click.Path(exists=True))
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
@click.option("--use_cal_default", is_flag=True, help="Use default calibration values")
@click.option(
    "--start/--no-start",
    default=True,
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
    start,
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

    if start:
        ts_start, delay = find_consensus_time(ctx.obj["fab group"])
        parameter_dict["start_time"] = ts_start

    configure_shepherd(
        ctx.obj["fab group"],
        "harvester",
        parameter_dict,
        ctx.obj["hostnames"],
        ctx.obj["verbose"],
    )

    if start:
        logger.debug(
            "Scheduling start of shepherd at %d (in ~ %.2f s)", ts_start, delay
        )
        start_shepherd(ctx.obj["fab group"], ctx.obj["hostnames"])


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
@click.option("--use_cal_default", is_flag=True, help="Use default calibration values")
@click.option(
    "--enable_io/--disable_io",
    default=True,
    help="Switch the GPIO level converter to targets on/off",
)
@click.option(
    "--io_sel_target_a/--io_sel_target_b",
    default=True,
    help="Choose Target that gets connected to IO",
)
@click.option(
    "--pwr_sel_target_a/--pwr_sel_target_b",
    default=True,
    help="Choose (main)Target that gets connected to virtual Source",
)
@click.option(
    "--aux_voltage",
    type=float,
    help="Set Voltage of auxiliary Power Source (second target)",
)
@click.option(
    "--virtsource",
    default={},
    help="Use the desired setting for the virtual source",
)
@click_config_file.configuration_option(provider=yamlprovider, implicit=False)
@click.option(
    "--start/--no-start",
    default=True,
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
    enable_target_io,
    sel_target_a_for_io,
    sel_target_a_for_pwr,
    aux_target_voltage,
    virtsource,
    start,
):

    fp_input = Path(input_path)
    if not fp_input.is_absolute():
        fp_input = Path("/var/shepherd/recordings") / input_path

    parameter_dict = {
        "input_path": str(fp_input),
        "force_overwrite": force_overwrite,
        "duration": duration,
        "use_cal_default": use_cal_default,
        "set_target_io_lvl_conv": enable_target_io,
        "sel_target_for_io": sel_target_a_for_io,
        "sel_target_for_pwr": sel_target_a_for_pwr,
        "aux_target_voltage": aux_target_voltage,
        "settings_virtsource": virtsource,
    }

    if output_path is not None:
        fp_output = Path(output_path)
        if not fp_output.is_absolute():
            fp_output = Path("/var/shepherd/recordings") / output_path

        parameter_dict["output_path"] = str(fp_output)

    if start:
        ts_start, delay = find_consensus_time(ctx.obj["fab group"])
        parameter_dict["start_time"] = ts_start

    configure_shepherd(
        ctx.obj["fab group"],
        "emulator",
        parameter_dict,
        ctx.obj["hostnames"],
        ctx.obj["verbose"],
    )

    if start:
        logger.debug(
            "Scheduling start of shepherd at %d (in ~ %.2f s)", ts_start, delay
        )
        start_shepherd(ctx.obj["fab group"], ctx.obj["hostnames"])


@cli.command(
    short_help="Start pre-configured shp-service (/etc/shepherd/config.yml, UNSYNCED)"
)
@click.pass_context
def start(ctx):
    if check_shepherd(ctx.obj["fab group"], ctx.obj["hostnames"]):
        logger.info("Shepherd still running, will skip this command!")
        sys.exit(1)
    else:
        start_shepherd(ctx.obj["fab group"], ctx.obj["hostnames"])
        logger.info("Shepherd started.")


@cli.command(short_help="Information about current shepherd measurement")
@click.pass_context
def check(ctx) -> None:
    ret = check_shepherd(ctx.obj["fab group"], ctx.obj["hostnames"])
    if ret:
        logger.info("Shepherd still running!")
        sys.exit(1)
    else:
        logger.info("Shepherd not running! (measurement is done)")


@cli.command(short_help="Stops any harvest/emulation")
@click.pass_context
def stop(ctx):
    for cnx in ctx.obj["fab group"]:
        cnx.sudo("systemctl stop shepherd", hide=True, warn=True)
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
    type=click.Path(),
    help="for safety only allowed: /var/shepherd/* or /etc/shepherd/*",
)
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
def distribute(ctx, filename, remote_path, force_overwrite):
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
        if not path_allowed:
            raise NameError(f"provided path was forbidden ('{remote_path}')")

    filename = Path(filename)
    tmp_path = Path("tmp") / filename.name
    xtr_arg = "-f" if force_overwrite else "-n"

    for cnx in ctx.obj["fab group"]:
        cnx.put(filename, Path("tmp") / filename.name)  # noqa: S108
        cnx.sudo(f"mv {xtr_arg} {tmp_path} {remote_path}")


@cli.command(short_help="Retrieves remote hdf file FILENAME and stores in in OUTDIR")
@click.argument("filename", type=click.Path())
@click.argument("outdir", type=click.Path(exists=True))
@click.option(
    "--timestamp", "-t", is_flag=True, help="Add current timestamp to measurement file"
)
@click.option(
    "--delete",
    "-d",
    is_flag=True,
    help="Delete the file from the remote filesystem after retrieval",
)
@click.option(
    "--stop",
    "-s",
    is_flag=True,
    help="Stop the on-going harvest/emulation process before retrieving the data",
)
@click.pass_context
def retrieve(ctx, filename, outdir, rename, delete, stop) -> None:
    """

    :param filename: remote file with absolute path or relative in '/var/shepherd/recordings/'
    :param outdir: local path to put the files in 'outdir/[node-name]/filename'
    :param rename:
    :param delete:
    :param stop:
    :return:
    """
    if stop:
        for cnx in ctx.obj["fab group"]:

            logger.info(
                "stopping shepherd service on %s", ctx.obj["hostnames"][cnx.host]
            )
            res = cnx.sudo("systemctl stop shepherd", hide=True, warn=True)

    time_str = time.strftime("%Y_%m_%dT%H_%M_%S")
    ts_end = time.time() + 30
    for cnx in ctx.obj["fab group"]:
        while True:
            res = cnx.sudo("systemctl status shepherd", hide=True, warn=True)
            if res.exited == 3:
                break
            if not stop or time.time() > ts_end:
                raise Exception(
                    f"shepherd not inactive on {ctx.obj['hostnames'][cnx.host]}"
                )
            time.sleep(1)

        target_path = Path(outdir) / ctx.obj["hostnames"][cnx.host]
        if not target_path.exists():
            logger.info("creating local dir %s", target_path)
            target_path.mkdir()

        if Path(filename).is_absolute():
            filepath = Path(filename)
        else:
            filepath = Path("/var/shepherd/recordings") / filename

        if rename:
            local_path = target_path / f"{filepath.stem}_{ time_str }.{filepath.suffix}"
        else:
            local_path = target_path / filepath.name

        logger.info(
            (
                "retrieving remote file %s from %s to local %s",
                filepath,
                ctx.obj["hostnames"][cnx.host],
                local_path,
            )
        )
        cnx.get(filepath, local=Path(local_path))
        if delete:
            logger.info(
                "deleting %s from remote %s",
                filepath,
                ctx.obj["hostnames"][cnx.host],
            )
            cnx.sudo(f"rm {str(filepath)}", hide=True)


def main():
    return cli(obj={})
