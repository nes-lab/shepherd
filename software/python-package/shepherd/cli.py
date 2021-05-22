# -*- coding: utf-8 -*-

"""
shepherd.cli
~~~~~
Provides the CLI utility 'shepherd-sheep', exposing most of shepherd's
functionality to a command line user.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
from typing import Dict

import click
import time
import pathlib
import logging
import sys
import signal
import zerorpc
import gevent
import yaml
from contextlib import ExitStack
import invoke
from pathlib import Path
import click_config_file
from periphery import GPIO

from shepherd.datalog import LogWriter
from shepherd.datalog import LogReader
from shepherd import sysfs_interface
from shepherd import record as run_record
from shepherd import emulate as run_emulate
from shepherd.calibration import CalibrationData
from shepherd import EEPROM
from shepherd import CapeData
from shepherd import ShepherdDebug
from shepherd.shepherd_io import gpio_pin_nums
from shepherd.launcher import Launcher
from shepherd.target_io import TargetIO

consoleHandler = logging.StreamHandler()
logger = logging.getLogger("shepherd")
logger.addHandler(consoleHandler)

# TODO: --length -l is now --duration -d -> correct docs
# TODO: --input --output is now --output_path -> correct docs
# TODO: --virtsource replaces vcap, is not optional anymore, maybe prepare preconfigured converters (bq-series) to choose from
# TODO: the options get repeated all the time, is it possible to define them upfront and just include them where needed?
# TODO: ditch sudo, add user to allow sys_fs-access and other things


def yamlprovider(file_path: str, cmd_name) -> Dict:
    logger.info(f"reading config from {file_path}")
    with open(file_path, "r") as config_data:
        full_config = yaml.safe_load(config_data)
    return full_config


@click.group(context_settings=dict(help_option_names=["-h", "--help"], obj={}))
@click.option("-v", "--verbose", count=True, default=1)
@click.pass_context
def cli(ctx, verbose):
    """ Shepherd: Synchronized Energy Harvesting Emulator and Recorder

    Args:
        ctx:
        verbose:

    Returns:

    """

    if verbose == 0:
        logger.setLevel(logging.ERROR)
    elif verbose == 1:
        logger.setLevel(logging.WARNING)
    elif verbose == 2:
        logger.setLevel(logging.INFO)
    elif verbose > 2:
        logger.setLevel(logging.DEBUG)


@cli.command(short_help="Turns auxiliary target power supply on or off")
@click.option("--on/--off", default=True)
@click.option("--voltage", type=float, help="Aux-Target supply voltage")
@click.option("--aux_sel_target_a/--aux_sel_target_b", default=True,
              help="Choose (main)Target that gets connected to virtual Source")
def aux_target_power(on: bool, voltage: float, sel_target_for_aux: bool):
    if not voltage:
        voltage = 3.0
    else:
        if not on:
            raise click.UsageError(
                "Can't set voltage, when Shepherd is switched off"
            )
    for pin_name in ["en_shepherd"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(on)
    for pin_name in ["target_pwr_sel"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(not sel_target_for_aux)
    cal = CalibrationData.from_default()
    sysfs_interface.write_dac_aux_voltage(cal, voltage)
    # NOTE: this FN needs persistent IO, (old GPIO-Lib)


@cli.command(
    short_help="Runs a command with given parameters. Mainly for use with config file.")
@click.option("--command", default="record", type=click.Choice(["record", "emulate"]))
@click.option("--parameters", default=dict())
@click_config_file.configuration_option(provider=yamlprovider, implicit=False)
@click.option("-v", "--verbose", count=True)
def run(command, parameters: Dict, verbose):

    if verbose is not None:
        if verbose == 0:
            logger.setLevel(logging.ERROR)
        elif verbose == 1:
            logger.setLevel(logging.WARNING)
        elif verbose == 2:
            logger.setLevel(logging.INFO)
        elif verbose > 2:
            logger.setLevel(logging.DEBUG)

    if not isinstance(parameters, Dict):
        raise click.BadParameter(f"parameter-argument is not dict, but {type(parameters)} (last occurred with alpha-version of click-lib)")

    # TODO: test input parameters before - crashes because of wrong lines are ugly
    if command == "record":
        if "output_path" in parameters.keys():
            parameters["output_path"] = Path(parameters["output_path"])
        run_record(**parameters)
    elif command == "emulate":
        if ("output_path" in parameters.keys()) and (parameters["output_path"] is not None):
            parameters["output_path"] = Path(parameters["output_path"])
        if "input_path" in parameters.keys():
            parameters["input_path"] = Path(parameters["input_path"])
        run_emulate(**parameters)
    else:
        raise click.BadParameter(f"command {command} not supported")


@cli.command(short_help="Record IV data")
@click.option("--output_path", "-o", type=click.Path(), default="/var/shepherd/recordings",
    help="Dir or file path for resulting hdf5 file",)
@click.option("--mode", type=click.Choice(["harvesting", "harvesting_test"]), default="harvesting",
    help="Record 'harvesting' or 'harvesting_test'-function data")
@click.option("--duration", "-d", type=float, help="Duration of recording in seconds")
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option("--no-calib", is_flag=True, help="Use default calibration values")
@click.option("--start-time", "-s", type=float,
    help="Desired start time in unix epoch time",)
@click.option("--warn-only/--no-warn-only", default=True, help="Warn only on errors")
def record(
    output_path,
    mode,
    duration,
    force_overwrite,
    no_calib,
    start_time,
    warn_only,
):
    run_record(
        output_path=Path(output_path),
        mode=mode,
        duration=duration,
        force_overwrite=force_overwrite,
        no_calib=no_calib,
        start_time=start_time,
        warn_only=warn_only,
    )


@cli.command(
    short_help="Emulate data, where INPUT is an hdf5 file containing harvesting data"
)
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output_path", "-o", type=click.Path(),
              help="Dir or file path for storing the power consumption data")
@click.option("--duration", "-d", type=float, help="Duration of recording in seconds")
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option("--no-calib", is_flag=True, help="Use default calibration values")
@click.option("--start-time", type=float, help="Desired start time in unix epoch time")
@click.option("--enable_io/--disable_io", default=True,
              help="Switch the GPIO level converter to targets on/off")
@click.option("--io_sel_target_a/--io_sel_target_b", default=True,
              help="Choose Target that gets connected to IO")
@click.option("--pwr_sel_target_a/--pwr_sel_target_b", default=True,
              help="Choose (main)Target that gets connected to virtual Source")
@click.option("--aux_voltage", type=float,
              help="Set Voltage of auxiliary Power Source (second target)")
@click.option("--virtsource", default=dict(), help="Use the desired setting for the virtual source")
@click_config_file.configuration_option(provider=yamlprovider, implicit=False)
@click.option("--warn-only/--no-warn-only", default=True, help="Warn only on errors")
def emulate(
    input_path,
    output_path,
    duration,
    force_overwrite,
    no_calib,
    start_time,
    enable_target_io,
    sel_target_a_for_io,
    sel_target_a_for_pwr,
    aux_target_voltage,
    virtsource,
    warn_only,
):
    if output_path is None:
        pl_store = None
    else:
        pl_store = Path(output_path)

    run_emulate(
        input_path=Path(input_path),
        output_path=pl_store,
        duration=duration,
        force_overwrite=force_overwrite,
        no_calib=no_calib,
        start_time=start_time,
        set_target_io_lvl_conv=enable_target_io,
        sel_target_for_io=sel_target_a_for_io,
        sel_target_for_pwr=sel_target_a_for_pwr,
        aux_target_voltage=aux_target_voltage,
        settings_virtsource=virtsource,
        warn_only=warn_only,
    )


@cli.group(
    context_settings=dict(help_option_names=["-h", "--help"], obj={}),
    short_help="Read/Write data from EEPROM",
)
def eeprom():
    pass


@eeprom.command(short_help="Write data to EEPROM")
@click.option("--infofile", "-i", type=click.Path(exists=True),
    help="YAML-formatted file with cape info")
@click.option("--version", "-v", type=str, default="00A0",
    help="Cape version number, e.g. 00A0")
@click.option("--serial_number", "-s", type=str,
    help="Cape serial number, e.g. 3219AAAA0001")
@click.option("--calibfile", "-c", type=click.Path(exists=True),
    help="YAML-formatted file with calibration data")
@click.option("--no-calib", is_flag=True, help="Use default calibration data")
def write(infofile, version, serial_number, calibfile, no_calib):
    if infofile is not None:
        if serial_number is not None or version is not None:
            raise click.UsageError(
                (
                    "--infofile and --version/--serial_number"
                    " are mutually exclusive"
                )
            )
        cape_data = CapeData.from_yaml(infofile)
        with EEPROM() as eeprom:
            eeprom.write_cape_data(cape_data)
    elif serial_number is not None or version is not None:
        if version is None or serial_number is None:
            raise click.UsageError(
                ("--version and --serial_number are required")
            )
        cape_data = CapeData.from_values(serial_number, version)
        with EEPROM() as eeprom:
            eeprom.write_cape_data(cape_data)

    if calibfile is not None:
        if no_calib:
            raise click.UsageError(
                "--no-calib and --calibfile are mutually exclusive"
            )
        calib = CalibrationData.from_yaml(calibfile)
        with EEPROM() as eeprom:
            cape_data = eeprom.write_calibration(calib)
    if no_calib:
        calib = CalibrationData.from_default()

        with EEPROM() as eeprom:
            eeprom.write_calibration(calib)


@eeprom.command(short_help="Read cape info and calibration data from EEPROM")
@click.option("--infofile", "-i", type=click.Path(),
    help="If provided, cape info data is dumped to this file")
@click.option("--calibfile", "-c", type=click.Path(),
    help="If provided, calibration data is dumped to this file")
def read(infofile, calibfile):

    with EEPROM() as eeprom:
        cape_data = eeprom.read_cape_data()
        calib = eeprom.read_calibration()

    if infofile:
        with open(infofile, "w") as f:
            f.write(repr(cape_data))
    else:
        print(repr(cape_data))

    if calibfile:
        with open(calibfile, "w") as f:
            f.write(repr(calib))
    else:
        print(repr(calib))


@eeprom.command(
    short_help="Convert calibration measurements to calibration data, where FILENAME is YAML-formatted file containing calibration measurements"
)
@click.argument("filename", type=click.Path(exists=True))
@click.option("--output_path", "-o", type=click.Path(),
    help="Path to resulting YAML-formatted calibration data file")
def make(filename, output_path):
    cd = CalibrationData.from_measurements(filename)
    if output_path is None:
        print(repr(cd))
    else:
        with open(output_path, "w") as f:
            f.write(repr(cd))


@cli.command(short_help="Start zerorpc server")
@click.option("--port", "-p", type=int, default=4242)
def rpc(port):

    logger.setLevel(logging.INFO)  # TODO: via argument
    shepherd_io = ShepherdDebug()
    shepherd_io.__enter__()
    logger.debug("Initialized shepherd debug interface")
    time.sleep(1)

    server = zerorpc.Server(shepherd_io)
    server.bind(f"tcp://0.0.0.0:{ port }")
    time.sleep(1)

    def stop_server():
        server.stop()
        shepherd_io.__exit__()
        sys.exit(0)

    gevent.signal(signal.SIGTERM, stop_server)
    gevent.signal(signal.SIGINT, stop_server)

    shepherd_io.start()
    logger.info("Started shepherd debug interface")
    server.run()


@cli.command(short_help="Start shepherd launcher")
@click.option("--led", "-l", type=int, default=22)
@click.option("--button", "-b", type=int, default=65)
def launcher(led, button):
    with Launcher(button, led) as lnch:
        lnch.run()


if __name__ == "__main__":
    cli()
