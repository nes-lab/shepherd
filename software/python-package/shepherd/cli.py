"""
shepherd.cli
~~~~~
Provides the CLI utility 'shepherd-sheep', exposing most of shepherd's
functionality to a command line user.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Dict
from typing import Optional

import chromalog
import click
import click_config_file
import gevent
import yaml
import zerorpc
from periphery import GPIO

from . import ShepherdDebug
from . import __version__
from . import get_verbose_level
from . import run_emulator
from . import run_recorder
from . import set_verbose_level
from . import sysfs_interface
from .calibration import CalibrationData
from .eeprom import EEPROM
from .eeprom import CapeData
from .launcher import Launcher
from .shepherd_io import gpio_pin_nums
from .sysfs_interface import check_sys_access
from .sysfs_interface import reload_kernel_module

chromalog.basicConfig()
logger = logging.getLogger("shp.cli")


# TODO: correct docs
# --length -l is now --duration -d ->
# --input --output is now --output_path -> correct docs
# --virtsource replaces vcap, is not optional anymore,
#   maybe prepare preconfigured converters (bq-series) to choose from
#   possible choices: nothing, converter-name like BQ25570 / BQ25504, path to yaml-config
#   -> vSource contains vharvester and vConverter
# - the options get repeated all the time, is it possible to define them
#   upfront and just include them where needed?
# - ditch sudo, add user to allow sys_fs-access and other things
# - default-cal -> use_cal_default
# - start-time -> start_time
# - sheep run record -> sheep run harvester, same with sheep record
# TODO: clean up internal naming only have harvest/emulate to
#       use harvester/emulator, even the commands should be
#       "sheep harvester config"


def yamlprovider(file_path: str, cmd_name: str) -> dict:
    logger.info("reading config from %s, cmd=%s", file_path, cmd_name)
    with open(file_path) as config_data:
        full_config = yaml.safe_load(config_data)
    return full_config


@click.group(context_settings={"help_option_names": ["-h", "--help"], "obj": {}})
@click.option(
    "-v",
    "--verbose",
    count=True,
    default=2,
    help="4 Levels, but level 4 has serious performance impact",
)
@click.option(
    "--version",
    is_flag=True,
    help="Prints version-info at start (combinable with -v)",
)
@click.pass_context
def cli(ctx: click.Context, verbose: int, version: bool):
    """Shepherd: Synchronized Energy Harvesting Emulator and Recorder"""
    set_verbose_level(verbose)
    if version:
        logger.info("Shepherd-Sheep v%s", __version__)
        logger.debug("Python v%s", sys.version)
        logger.debug("Click v%s", click.__version__)
    check_sys_access()
    if not ctx.invoked_subcommand:
        click.echo("Please specify a valid command")


@cli.command(short_help="Turns target power supply on or off (i.e. for programming)")
@click.option("--on/--off", default=True)
@click.option(
    "--voltage",
    "-v",
    type=click.FLOAT,
    default=3.0,
    help="Target supply voltage",
)
@click.option(
    "--gpio_pass/--gpio_omit",
    default=True,
    help="Route UART, Programmer-Pins and other GPIO to this target",
)
@click.option(
    "--sel_a/--sel_b",
    default=True,
    help="Choose (main)Target that gets connected to virtual Source",
)
def target_power(on: bool, voltage: float, gpio_pass: bool, sel_a: bool):
    if not on:
        voltage = 0.0
    # TODO: output would be nicer when this uses shepherdDebug as base
    for pin_name in ["en_shepherd"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(on)
        logger.info("Shepherd-State \t= %s", "enabled" if on else "disabled")
    for pin_name in ["target_pwr_sel"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(not sel_a)  # switched because rail A is AUX
        logger.info("Select Target \t= %s", "A" if sel_a else "B")
    for pin_name in ["target_io_sel"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(sel_a)
    for pin_name in ["target_io_en"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(gpio_pass)
        logger.info("IO passing \t= %s", "enabled" if gpio_pass else "disabled")
    cal = CalibrationData.from_default()
    logger.info("Target Voltage \t= %.3f V", voltage)
    sysfs_interface.write_dac_aux_voltage(cal, voltage)
    sysfs_interface.write_mode("emulator", force=True)
    sysfs_interface.set_stop(force=True)  # forces reset
    logger.info("Re-Initialized PRU to finalize settings")
    # NOTE: this FN needs persistent IO, (old GPIO-Lib)


@cli.command(
    short_help="Runs a mode with given parameters. Mainly for use with config file.",
)
@click.option(
    "--mode",
    default="harvester",
    type=click.Choice(["harvester", "emulator"]),
)
@click.option("--parameters", default={}, type=click.UNPROCESSED)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="4 Levels, but level 4 has serious performance impact",
)
@click_config_file.configuration_option(provider=yamlprovider, implicit=False)
def run(mode: str, parameters: dict, verbose: int):
    set_verbose_level(verbose)

    if not isinstance(parameters, Dict):
        raise click.BadParameter(
            f"parameter-argument is not dict, but {type(parameters)} "
            "(last occurred with v8-alpha-version of click-lib)",
        )

    # TODO: test input parameters before - crashes because of wrong parameters are ugly
    logger.debug("CLI did process run()")
    if mode == "harvester":
        if "output_path" in parameters:
            parameters["output_path"] = Path(parameters["output_path"])
        run_recorder(**parameters)
    elif mode == "emulator":
        if ("output_path" in parameters) and (parameters["output_path"] is not None):
            parameters["output_path"] = Path(parameters["output_path"])
        if "input_path" in parameters:
            parameters["input_path"] = Path(parameters["input_path"])
        emu_translator = {
            "aux_voltage": "aux_target_voltage",
        }
        for key, value in emu_translator.items():
            if key in parameters:
                parameters[value] = parameters[key]
                parameters.pop(key)
        run_emulator(**parameters)
    else:
        raise click.BadParameter(f"command '{mode}' not supported")


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
    "--start_time",
    "-s",
    type=click.FLOAT,
    help="Desired start time in unix epoch time",
)
@click.option("--warn-only/--no-warn-only", default=True, help="Warn only on errors")
def harvester(
    output_path: Path,
    algorithm: Optional[str],
    duration: Optional[float],
    force_overwrite: bool,
    use_cal_default: bool,
    start_time: Optional[float],
    warn_only: bool,
):
    run_recorder(
        output_path=Path(output_path),
        harvester=algorithm,
        duration=duration,
        force_overwrite=force_overwrite,
        use_cal_default=use_cal_default,
        start_time=start_time,
        warn_only=warn_only,
    )


@cli.command(
    short_help="Emulate data, where INPUT is an hdf5 file containing harvesting data",
)
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "--output_path",
    "-o",
    type=click.Path(),
    default="/var/shepherd/recordings/",
    help="Dir or file path for storing the power consumption data",
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
    "--start_time",
    "-s",
    type=click.FLOAT,
    help="Desired start time in unix epoch time",
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
    help="Choose Target 'A' or 'B' that gets connected to IO",
)
@click.option(
    "--pwr_target",
    type=click.Choice(["A", "B"]),
    default="A",
    help="Choose (main)Target 'A' or 'B' that gets connected to virtual Source / current-monitor",
)
@click.option(
    "--aux_voltage",
    "-x",
    type=click.FLOAT,
    default=0.0,
    help="Set Voltage of auxiliary Power Source (second target). \n"
    "- set 0-4.5 for specific const voltage, \n"
    "- 'mid' for intermediate voltage (vsource storage cap), \n"
    "- True or 'main' to mirror main target voltage",
)
@click.option(
    "--virtsource",
    "-a",  # -v & -s already taken, so keep it consistent with hrv (algorithm)
    type=click.STRING,
    default="direct",
    help="Use the desired setting for the virtual source, provide yaml or name like BQ25570",
)
@click.option(
    "--uart_baudrate",
    "-b",
    type=click.INT,
    default=None,
    help="Enable UART-Logging for target by setting a baudrate",
)
@click.option("--warn-only/--no-warn-only", default=True, help="Warn only on errors")
@click.option(
    "--skip_log_voltage",
    is_flag=True,
    help="reduce file-size by omitting voltage-logging",
)
@click.option(
    "--skip_log_current",
    is_flag=True,
    help="reduce file-size by omitting current-logging",
)
@click.option(
    "--skip_log_gpio",
    is_flag=True,
    help="reduce file-size by omitting gpio-logging",
)
@click.option(
    "--log_mid_voltage",
    is_flag=True,
    help="record / log virtual intermediate (cap-)voltage and -current (out) "
    "instead of output-voltage and -current",
)
def emulator(
    input_path: Path,
    output_path: Path,
    duration: Optional[float],
    force_overwrite: bool,
    use_cal_default: bool,
    start_time: Optional[float],
    enable_io: bool,
    io_target: str,
    pwr_target: str,
    aux_voltage: float,
    virtsource: str,
    uart_baudrate: Optional[int],
    warn_only: bool,
    skip_log_voltage: bool,
    skip_log_current: bool,
    skip_log_gpio: bool,
    log_mid_voltage: bool,
):
    if output_path is None:
        pl_store = None
    else:
        pl_store = Path(output_path)

    run_emulator(
        input_path=Path(input_path),
        output_path=pl_store,
        duration=duration,
        force_overwrite=force_overwrite,
        use_cal_default=use_cal_default,
        start_time=start_time,
        enable_io=enable_io,
        io_target=io_target,
        pwr_target=pwr_target,
        aux_target_voltage=aux_voltage,
        virtsource=virtsource,
        log_intermediate_voltage=log_mid_voltage,
        uart_baudrate=uart_baudrate,
        warn_only=warn_only,
        skip_log_voltage=skip_log_voltage,
        skip_log_current=skip_log_current,
        skip_log_gpio=skip_log_gpio,
    )


@cli.group(
    context_settings={"help_option_names": ["-h", "--help"], "obj": {}},
    short_help="Read/Write data from EEPROM",
)
def eeprom():
    pass


@eeprom.command(short_help="Write data to EEPROM")
@click.option(
    "--info_file",
    "-i",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
    help="YAML-formatted file with cape info",
)
@click.option(
    "--version",
    "-v",
    type=click.STRING,
    help="Cape version number, max 4 Char, e.g. 24A0, reflecting hardware revision",
)
@click.option(
    "--serial_number",
    "-s",
    type=click.STRING,
    help="Cape serial number, max 12 Char, e.g. HRV_EMU_1001, reflecting capability & increment",
)
@click.option(
    "--cal_date",
    "-d",
    type=click.STRING,
    help="Cape calibration date, max 10 Char, e.g. 2022-01-21, reflecting year-month-day",
)
@click.option(
    "--cal_file",
    "-c",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
    help="YAML-formatted file with calibration data",
)
def write(
    info_file: Optional[Path],
    version: Optional[str],
    serial_number: Optional[str],
    cal_date: Optional[str],
    cal_file: Optional[Path],
):
    if info_file is not None:
        cape_data = CapeData.from_yaml(info_file)
        # overwrite fields that were provided additionally
        if version is not None:
            cape_data.data["version"] = version
        if serial_number is not None:
            cape_data.data["serial_number"] = serial_number
        if cal_date is not None:
            cape_data.data["cal_date"] = cal_date
    else:
        cape_data = CapeData.from_values(serial_number, version, cal_date)

    if "version" not in cape_data.data:
        raise click.UsageError("--version is required")
    if "serial_number" not in cape_data.data:
        raise click.UsageError("--serial_number is required")
    if "cal_date" not in cape_data.data:
        raise click.UsageError("--cal_date is required")

    with EEPROM() as storage:
        storage.write_cape_data(cape_data)

    if cal_file is not None:
        cal = CalibrationData.from_yaml(cal_file)
        with EEPROM() as storage:
            storage.write_calibration(cal)


@eeprom.command(short_help="Read cape info and calibration data from EEPROM")
@click.option(
    "--info_file",
    "-i",
    type=click.Path(),
    help="If provided, cape info data is dumped to this file",
)
@click.option(
    "--cal_file",
    "-c",
    type=click.Path(),
    help="If provided, calibration data is dumped to this file",
)
def read(info_file: Optional[Path], cal_file: Optional[Path]):
    if get_verbose_level() < 2:
        set_verbose_level(2)

    with EEPROM() as storage:
        cape_data = storage.read_cape_data()
        cal = storage.read_calibration()

    if info_file:
        with open(info_file, "w") as f:
            f.write(repr(cape_data))
    else:
        logger.info(repr(cape_data))

    if cal_file:
        with open(cal_file, "w") as f:
            f.write(repr(cal))
    else:
        logger.info(repr(cal))


@eeprom.command(
    short_help="Convert calibration measurements to calibration data, "
    "where FILENAME is YAML-formatted file "
    "containing calibration measurements",
)
@click.argument(
    "filename",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
)
@click.option(
    "--output_path",
    "-o",
    type=click.Path(),
    help="Path to resulting YAML-formatted calibration data file",
)
def make(filename: Path, output_path: Optional[Path]):
    if get_verbose_level() < 2:
        set_verbose_level(2)

    cd = CalibrationData.from_measurements(filename)
    if output_path is None:
        logger.info(repr(cd))
    else:
        with open(output_path, "w") as f:
            f.write(repr(cd))


@cli.command(short_help="Start zerorpc server")
@click.option("--port", "-p", type=click.INT, default=4242)
def rpc(port: Optional[int]):
    shepherd_io = ShepherdDebug()
    shepherd_io.__enter__()
    logger.info("Shepherd Debug Interface: Initialized")
    time.sleep(1)

    server = zerorpc.Server(shepherd_io)
    server.bind(f"tcp://0.0.0.0:{ port }")
    time.sleep(1)

    def stop_server():
        server.stop()
        shepherd_io.__exit__()
        sys.exit(0)

    gevent.signal_handler(signal.SIGTERM, stop_server)
    gevent.signal_handler(signal.SIGINT, stop_server)

    shepherd_io.start()
    logger.info("Shepherd RPC Interface: Started")
    server.run()


@cli.command(short_help="Start shepherd launcher")
@click.option("--led", "-l", type=click.INT, default=22)
@click.option("--button", "-b", type=click.INT, default=65)
def launcher(led: int, button: int):
    with Launcher(button, led) as launch:
        launch.run()


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
    "--datarate",
    "-d",
    type=click.INT,
    default=500_000,
    help="Bit rate of Programmer (bit/s)",
)
@click.option(
    "--target",
    "-t",
    type=click.Choice(["nrf52", "msp430"]),
    default="nrf52",
    help="Target MCU",
)
@click.option(
    "--prog1/--prog2",
    default=True,
    help="Choose Programming-Pins of Target-Port (only valid for SBW & SWD)",
)
@click.option(
    "--simulate",
    is_flag=True,
    help="dry-run the programmer - no data gets written",
)
def programmer(
    firmware_file: Path,
    sel_a: bool,
    voltage: float,
    datarate: int,
    target: str,
    prog1: bool,
    simulate: bool,
):
    with ShepherdDebug(use_io=False) as sd:
        sd.select_target_for_power_tracking(sel_a=not sel_a)
        sd.set_power_state_emulator(True)
        sd.select_target_for_io_interface(sel_a=sel_a)
        sd.set_io_level_converter(True)

        cal = CalibrationData.from_default()
        sysfs_interface.write_dac_aux_voltage(cal, voltage)
        # switching target may restart pru
        sysfs_interface.wait_for_state("idle", 5)

        protocol_dict = {
            "nrf52": "SWD",
            "msp430": "SBW",
        }
        sysfs_interface.load_pru0_firmware(protocol_dict[target])
        failed = False

        with open(firmware_file, "rb") as fw:
            try:
                sd.shared_mem.write_firmware(fw.read())
                if simulate:
                    target = "dummy"
                if prog1:
                    sysfs_interface.write_programmer_ctrl(target, datarate, 5, 4, 10)
                else:
                    sysfs_interface.write_programmer_ctrl(target, datarate, 8, 9, 11)
                logger.info("Programmer initialized, will start now")
                sysfs_interface.start_programmer()
            except OSError:
                logger.error("OSError - Failed to initialize Programmer")
                failed = True
            except ValueError as xpt:
                logger.exception("ValueError: %s", str(xpt))  # noqa: G200
                failed = True

        state = "init"
        while state != "idle" and not failed:
            logger.info("Programming in progress,\tstate = %s", state)
            time.sleep(1)
            state = sysfs_interface.check_programmer()
            if "error" in state:
                logger.error("SystemError - Failed during Programming")
                failed = True
            # TODO: programmer can hang in "starting", should restart automatically then
        if failed:
            logger.info("Programming - Procedure failed - will exit now!")
        else:
            logger.info("Finished Programming!")
        logger.debug("\tshepherdState   = %s", sysfs_interface.get_state())
        logger.debug("\tprogrammerState = %s", state)
        logger.debug("\tprogrammerCtrl  = %s", sysfs_interface.read_programmer_ctrl())

    sysfs_interface.load_pru0_firmware("shepherd")
    sys.exit(int(failed))


@cli.command(
    short_help="Reloads the shepherd-kernel-module",
    context_settings={"ignore_unknown_options": True},
)
def fix():
    reload_kernel_module()


if __name__ == "__main__":
    cli()
