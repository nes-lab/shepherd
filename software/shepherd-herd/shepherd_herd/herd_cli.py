import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import shepherd_core
import typer
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.testbed import ProgrammerProtocol
from shepherd_core.data_models.testbed import TargetPort
from shepherd_core.inventory import Inventory

from . import __version__
from .herd import Herd
from .logger import activate_verbose
from .logger import logger as log


def exit_gracefully(*args) -> None:  # type: ignore
    log.warning("Aborted!")
    sys.exit(0)


def cli_setup_callback(verbose: bool = False, print_version: bool = False) -> None:
    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)

    if verbose:
        activate_verbose()

    if print_version:
        log.info("Shepherd-Cal v%s", __version__)
        log.debug("Shepherd-Core v%s", shepherd_core.__version__)
        log.debug("Python v%s", sys.version)
        log.debug("Typer v%s", typer.__version__)
        log.debug("Click v%s", click.__version__)


cli = typer.Typer(help="Control-Instance for Shepherd-Testbed-Instances")

# sheep-related params
invent_opt_t = typer.Option(
    None,
    "-i",
    help="List of target hosts as comma-separated string or path to ansible-style yaml config",
)
limit_opt_t = typer.Option(
    None,
    "-l",
    help="Comma-separated list of hosts to limit execution to",
)
user_opt_t = typer.Option(None, "-u", help="User name for login to nodes")
key_opt_t = typer.Option(None, "-k", help="Path to private ssh key file")
verbose_opt_t = typer.Option(
    False,
    "-v",
    is_flag=True,
    help="Report at debug- instead of info-level",
)
version_opt_t = typer.Option(
    False, is_flag=True, help="Prints version-infos (combinable with -v)"
)
# oddity -> first implicit parameters are (default, [longname,] shortname)


# #############################################################################
#                               Misc-Commands
# #############################################################################

# unique inputs
restart_opt_t = typer.Option(False, "-r", is_flag=True, help="Reboot")
cmd_arg_t = typer.Argument(default=..., help="Shell-command to execute")
sudo_opt_t = typer.Option(False, "-s", is_flag=True, help="Run command as superuser")
opath_arg_t = typer.Argument(
    default=Path("./"),
    dir_okay=True,
    file_okay=False,
    exists=True,
    help="save-file, will be generic with timestamp if not provided",
)


@cli.command(help="Power off shepherd nodes")
def poweroff(
    restart: bool = restart_opt_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
):
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    exit_code = herd.poweroff(restart)
    sys.exit(exit_code)


@cli.command(help="Run COMMAND on the shell")
def shell_cmd(
    command: str = cmd_arg_t,
    sudo: bool = sudo_opt_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
):
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    replies = herd.run_cmd(sudo, command)
    herd.print_output(replies, 2)  # info-level
    exit_code = max([reply.exited for reply in replies.values()])
    sys.exit(exit_code)


@cli.command(help="Collects information about the hosts")
def inventorize(
    output_path: Path = opath_arg_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
) -> None:
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    file_path = Path("/var/shepherd/inventory.yaml")
    herd.run_cmd(
        sudo=True,
        cmd=f"shepherd-sheep inventorize --output_path {file_path.as_posix()}",
    )
    server_inv = Inventory.collect()
    output_path = Path(output_path)
    server_inv.to_file(path=Path(output_path) / "inventory_server.yaml", minimal=True)
    failed = herd.get_file(
        file_path,
        output_path,
        timestamp=False,
        separate=False,
        delete_src=True,
    )
    # TODO: best case - add all to one file or a new inventories-model?
    sys.exit(failed)
    # TODO: decide how to handle this. there is a typer-fn for that, also just return?


# #############################################################################
#                               Task-Handling
# #############################################################################

cfg_arg_t = typer.Argument(
    ...,
    exists=True,
    readable=True,
    file_okay=True,
    dir_okay=False,
    help="YAML-file with wrapped Task-model",
)
attach_opt_t = typer.Option(False, "-a", is_flag=True, help="Wait and receive output")


@cli.command(
    help="Runs a task or set of tasks",
)
def run(
    config: Path = cfg_arg_t,
    attach: bool = attach_opt_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
):
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    if attach:
        remote_path = Path("/etc/shepherd/config_for_herd.yaml")
        herd.put_file(config, remote_path, force_overwrite=True)
        command = f"shepherd-sheep -vvvv run {remote_path.as_posix()}"
        replies = herd.run_cmd(sudo=True, cmd=command)
        exit_code = max([reply.exited for reply in replies.values()])
        if exit_code:
            log.error("Programming - Procedure failed - will exit now!")
        herd.print_output(replies, 3)  # requires debug level
        sys.exit(exit_code)
    else:
        remote_path = Path("/etc/shepherd/config.yaml")
        herd.put_file(config, remote_path, force_overwrite=True)
        exit_code = herd.start_measurement()
        log.info("Shepherd started.")
        if exit_code > 0:
            log.debug("-> max exit-code = %d", exit_code)


opath_opt_t = typer.Option(
    Herd.path_default,
    "--output-path",
    "-o",
    dir_okay=True,
    file_okay=True,
    exists=False,
    help="Dir or file path for resulting hdf5 file",
)
vhrv_opt_t = typer.Option(
    "mppt_opt",
    "--virtual-harvester",
    "-a",
    help="Choose one of the predefined virtual harvesters",
)
dur_opt_t = typer.Option(
    None,
    "--duration",
    "-d",
    help="Duration of recording in seconds",
)
force_ow_opt_t = typer.Option(
    False, "--force-overwrite", "-f", is_flag=True, help="Overwrite existing file"
)
cal_opt_t = typer.Option(
    False,
    "--use-cal-default",
    "-c",
    is_flag=True,
    help="Use default calibration values",
)
nstart_opt_t = typer.Option(
    False,
    "--no-start",
    "-n",
    is_flag=True,
    help="Start shepherd synchronized after uploading config",
)


@cli.command(help="Record IV data from a harvest-source")
def harvest(
    output_path: Path = opath_opt_t,
    virtual_harvester: str = vhrv_opt_t,
    duration: Optional[float] = dur_opt_t,
    force_overwrite: bool = force_ow_opt_t,
    use_cal_default: bool = cal_opt_t,
    no_start: bool = nstart_opt_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
):
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    kwargs = {
        "output_path": output_path,
        "virtual_harvester": virtual_harvester,
        "duration": duration,
        "force_overwrite": force_overwrite,
        "use_cal_default": use_cal_default,
    }
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

    task = HarvestTask(**kwargs)
    herd.transfer_task(task)

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


# TODO: switch to local file for input?
ifile_arg_t = typer.Argument(
    ..., file_okay=True, dir_okay=False, exists=True, readable=True
)

en_io_opt_t = typer.Option(
    True,
    "--enable-io/--disable-io",
    help="Switch the GPIO level converter to targets on/off",
)
pio_opt_t = typer.Option(
    "A",
    "--io-port",
    click_type=click.Choice(["A", "B"]),
    help="Choose Target that gets connected to IO",
)
ppwr_opt_t = typer.Option(
    "A",
    "--pwr-port",
    click_type=click.Choice(["A", "B"]),
    help="Choose (main)Target that gets connected to virtual Source / current-monitor",
)
vaux_opt_t = typer.Option(
    0.0,
    "--voltage-aux",
    "-x",
    help="Set Voltage of auxiliary Power Source (second target)",
)
# -v & -s already taken for sheep, so keep it consistent with hrv (algorithm)
vsrc_opt_t = typer.Option(
    "direct",
    "--virtual-source",
    "-a",
    help="Use the desired setting for the virtual source",
)


@cli.command(
    help="Emulate data, where INPUT is an hdf5 file on the sheep containing harvesting data",
)
def emulate(
    input_file: Path = ifile_arg_t,
    output_path: Path = opath_opt_t,
    duration: Optional[float] = dur_opt_t,
    force_overwrite: bool = force_ow_opt_t,
    use_cal_default: bool = cal_opt_t,
    enable_io: bool = en_io_opt_t,
    io_port: str = pio_opt_t,
    pwr_port: str = ppwr_opt_t,
    voltage_aux: str = vaux_opt_t,
    virtual_source: str = vsrc_opt_t,
    no_start: bool = nstart_opt_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
):
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    kwargs = {
        "input_file": input_file,
        "output_path": output_path,
        "duration": duration,
        "force_overwrite": force_overwrite,
        "use_cal_default": use_cal_default,
        "enable_io": enable_io,
        "io_port": io_port,
        "pwr_port": pwr_port,
        "voltage_aux": voltage_aux,
        "virtual_source": virtual_source,
    }
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

    task = EmulationTask(**kwargs)
    herd.transfer_task(task)

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
    help="Start pre-configured shp-service (/etc/shepherd/config.yml, UNSYNCED)",
)
def start(
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
) -> None:
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    if herd.check_status():
        log.info("Shepherd still active, will skip this command!")
        sys.exit(1)
    else:
        exit_code = herd.start_measurement()
        log.info("Shepherd started.")
        if exit_code > 0:
            log.debug("-> max exit-code = %d", exit_code)


@cli.command(help="Information about current state of shepherd measurement")
def status(
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
) -> None:
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    if herd.check_status():
        log.info("Shepherd still active!")
        sys.exit(1)
    else:
        log.info("Shepherd not active! (measurement is done)")


@cli.command(help="Stops any harvest/emulation")
def stop(
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
) -> None:
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    exit_code = herd.stop_measurement()
    log.info("Shepherd stopped.")
    if exit_code > 0:
        log.debug("-> max exit-code = %d", exit_code)


# #############################################################################
#                               File Handling
# #############################################################################

rpath_opt_t = typer.Option(
    Herd.path_default,
    "--remote-path",
    "-r",
    help="for safety only allowed: /var/shepherd/* or /etc/shepherd/*",
)


@cli.command(
    help="Uploads a file FILENAME to the remote node, stored in in REMOTE_PATH",
)
def distribute(
    filename: Path = ifile_arg_t,
    remote_path: Path = rpath_opt_t,
    force_overwrite: bool = force_ow_opt_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
):
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    herd.put_file(filename, remote_path, force_overwrite)


file_arg_t = typer.Argument(..., help=f"remote file with absolute path or relative in '{Herd.path_default.as_posix()}'")
dout_arg_t = typer.Argument(..., exists=True,
        file_okay=False,
        dir_okay=True, help="local path to put the files in 'outdir/[node-name]/filename'")
ts_opt_t = typer.Option(False,
    "--timestamp",
    "-t",
    is_flag=True,
    help="Add current timestamp to measurement file",
)
sepa_opt_t = typer.Option(False, "--separate",
    "-s",
    is_flag=True,
    help="Every remote node gets own subdirectory",
)
del_opt_t = typer.Option(False,
    "--delete",
    "-d",
    is_flag=True,
    help="Delete the file from the remote filesystem after retrieval",
)
force_stop_opt_t = typer.Option(False, "--force-stop",
    "-f",
    is_flag=True,
    help="Stop the on-going harvest/emulation process before retrieving the data",
)


@cli.command(help="Retrieves remote hdf file FILENAME and stores in in OUTDIR")
def retrieve(
    filename: Path = file_arg_t,
    outdir: Path = dout_arg_t,
    timestamp: bool = ts_opt_t,
    separate: bool = sepa_opt_t,
    delete: bool = del_opt_t,
    force_stop: bool = force_stop_opt_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
) -> None:
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    if force_stop:
        herd.stop_measurement()
        if herd.await_stop(timeout=30):
            raise Exception("shepherd still active after timeout")

    failed = herd.get_file(filename, outdir, timestamp, separate, delete)
    sys.exit(failed)


# #############################################################################
#                               Pru Programmer
# #############################################################################

ifw_arg_t = typer.Argument(..., exists=True, file_okay=True, dir_okay=False, readable=True, help="Hex-File to program to target")
tgt_port_opt_t = typer.Option("A", "--target-port",
    "-p",
    click_type=click.Choice(["A", "B"]),
    help="Choose Target-Port of Cape for programming",
)
mcu_port_opt_t = typer.Option(1,
    "--mcu-port",
    "-m",
    help="Choose MCU on Target-Port (only valid for SBW & SWD)",
)
volt_opt_t = typer.Option(3.0,
    "--voltage",
    "-v",
    help="Target supply voltage",
)
drate_opt_t = typer.Option(500_000,
    "--datarate",
    "-d",
    help="Bit rate of Programmer (bit/s)",
)
mcu_type_opt_t = typer.Option("nrf52",
    "--mcu-type",
    "-t",
    click_type=click.Choice(["nrf52", "msp430"]),
    help="Target MCU",
)
sim_opt_t = typer.Option(False,
    "--simulate",
    is_flag=True,
    help="dry-run the programmer - no data gets written",
)

@cli.command(help="Programmer for Target-Controller")
def program(  # TODO **kwargs,
    firmware_file: Path = ifw_arg_t,
    target_port: str = tgt_port_opt_t,
    mcu_port: int = mcu_port_opt_t,
        voltage: float = volt_opt_t,
        datarate: int = drate_opt_t,
        mcu_type: str = mcu_type_opt_t,
        simulate: bool = sim_opt_t,
    # sheep-related params
    inventory: Optional[str] = invent_opt_t,
    limit: Optional[str] = limit_opt_t,
    user: Optional[str] = user_opt_t,
    key_filepath: Optional[Path] = key_opt_t,
    verbose: bool = verbose_opt_t,
    version: bool = version_opt_t,
):
    cli_setup_callback(verbose, version)
    herd = Herd(inventory, limit, user, key_filepath)
    kwargs = {
        "firmware_file": firmware_file,
        "mcu_port": mcu_port,
        "voltage": voltage,
        "datarate": datarate,
        "mcu_type": mcu_type,
        "simulate": simulate,
              }
    tmp_file = "/tmp/target_image.hex"  # noqa: S108
    cfg_path = Path("/etc/shepherd/config_for_herd.yaml")

    herd.put_file(kwargs["firmware_file"], tmp_file, force_overwrite=True)
    protocol_dict = {
        "nrf52": ProgrammerProtocol.swd,
        "msp430": ProgrammerProtocol.sbw,
    }
    kwargs["protocol"] = protocol_dict[kwargs["mcu_type"]]
    kwargs["firmware_file"] = Path(tmp_file)
    task = ProgrammingTask(**kwargs)
    herd.transfer_task(task, cfg_path)

    command = f"shepherd-sheep -vvv run {cfg_path.as_posix()}"
    replies = herd.run_cmd(sudo=True, cmd=command)
    exit_code = max([reply.exited for reply in replies.values()])
    if exit_code:
        log.error("Programming - Procedure failed - will exit now!")
    herd.print_output(replies, 3)  # requires debug level
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
