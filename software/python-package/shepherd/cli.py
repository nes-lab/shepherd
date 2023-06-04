"""
shepherd.cli
~~~~~
Provides the CLI utility 'shepherd-sheep', exposing most of shepherd's
functionality to a command line user.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import signal
import sys
import time
from pathlib import Path
from typing import Dict
from typing import Optional

import click
import click_config_file
import gevent
import yaml
import zerorpc
from periphery import GPIO
from shepherd_core import CalibrationCape
from .logger import get_verbose_level
from .logger import set_verbose_level
from shepherd_core.data_models.base.cal_measurement import CalMeasurementCape
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.testbed import ProgrammerProtocol

from . import __version__
from . import run_emulator
from . import run_harvester
from . import run_programmer
from . import sysfs_interface
from .eeprom import EEPROM
from .eeprom import CapeData
from .launcher import Launcher
from .logger import log
from .shepherd_debug import ShepherdDebug
from .shepherd_io import gpio_pin_nums
from .sysfs_interface import check_sys_access
from .sysfs_interface import reload_kernel_module

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
# - cleaned up internal naming (only harvester/emulator instead of record)
#   - TODO: even the commands should be "sheep harvester config"
# - redone programmer, emulation


def yamlprovider(file_path: str, cmd_name: str) -> dict:
    log.info("reading config from %s, cmd=%s", file_path, cmd_name)
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
        log.info("Shepherd-Sheep v%s", __version__)
        log.debug("Python v%s", sys.version)
        log.debug("Click v%s", click.__version__)
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
        log.info("Shepherd-State \t= %s", "enabled" if on else "disabled")
    for pin_name in ["target_pwr_sel"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(not sel_a)  # switched because rail A is AUX
        log.info("Select Target \t= %s", "A" if sel_a else "B")
    for pin_name in ["target_io_sel"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(sel_a)
    for pin_name in ["target_io_en"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(gpio_pass)
        log.info("IO passing \t= %s", "enabled" if gpio_pass else "disabled")
    log.info("Target Voltage \t= %.3f V", voltage)
    sysfs_interface.write_dac_aux_voltage(voltage)
    sysfs_interface.write_mode("emulator", force=True)
    sysfs_interface.set_stop(force=True)  # forces reset
    log.info("Re-Initialized PRU to finalize settings")
    # NOTE: this FN needs persistent IO, (old GPIO-Lib)


@cli.command(
    short_help="Runs a mode with given parameters. Mainly for use with config file.",
)
@click.option(
    "--mode",
    type=click.Choice(["harvest", "emulation"]),
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

    log.debug("CLI did process run()")
    if mode == "harvester":
        cfg = HarvestTask(**parameters)
        run_harvester(cfg)
    elif mode == "emulator":
        cfg = EmulationTask(**parameters)
        run_emulator(cfg)
    else:
        raise click.BadParameter(f"command '{mode}' not supported")


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
        # overwrite parameters that were provided additionally
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
        cal = CalibrationCape.from_file(cal_file)
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
        log.info(repr(cape_data))

    if cal_file:
        with open(cal_file, "w") as f:
            f.write(repr(cal))
    else:
        log.info(repr(cal))


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

    cal_cape = CalMeasurementCape.from_file(filename).to_cal()
    if output_path is None:
        log.info(repr(cal_cape))
    else:
        cal_cape.to_file(output_path)


@cli.command(short_help="Start zerorpc server")
@click.option("--port", "-p", type=click.INT, default=4242)
def rpc(port: Optional[int]):
    shepherd_io = ShepherdDebug()
    shepherd_io.__enter__()
    log.info("Shepherd Debug Interface: Initialized")
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
    log.info("Shepherd RPC Interface: Started")
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
def programmer(**kwargs):
    protocol_dict = {
        "nrf52": ProgrammerProtocol.swd,
        "msp430": ProgrammerProtocol.sbw,
    }
    kwargs["protocol"] = protocol_dict[kwargs["mcu_type"]]
    cfg = ProgrammingTask(**kwargs)
    run_programmer(cfg)


@cli.command(
    short_help="Reloads the shepherd-kernel-module",
    context_settings={"ignore_unknown_options": True},
)
def fix():
    reload_kernel_module()


if __name__ == "__main__":
    cli()
