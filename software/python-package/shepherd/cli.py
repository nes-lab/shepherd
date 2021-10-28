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
import logging
import sys
import signal
import zerorpc
import gevent
import yaml
from pathlib import Path
import click_config_file
from periphery import GPIO

from shepherd import sysfs_interface
from shepherd import record as run_record
from shepherd import emulate as run_emulate
from shepherd.calibration import CalibrationData
from shepherd import EEPROM
from shepherd import CapeData
from shepherd import ShepherdDebug
from shepherd import set_verbose_level
from shepherd.shepherd_io import gpio_pin_nums
from shepherd.launcher import Launcher

consoleHandler = logging.StreamHandler()
logger = logging.getLogger("shepherd")
logger.addHandler(consoleHandler)

# TODO: correct docs
# --length -l is now --duration -d ->
# --input --output is now --output_path -> correct docs
# --virtsource replaces vcap, is not optional anymore, maybe prepare preconfigured converters (bq-series) to choose from
#          possible choices: nothing, regulator-name like BQ25570 / BQ25504, path to yaml-config
# - the options get repeated all the time, is it possible to define them upfront and just include them where needed?
# - ditch sudo, add user to allow sys_fs-access and other things


def yamlprovider(file_path: str, cmd_name) -> Dict:
    logger.info(f"reading config from {file_path}, cmd={cmd_name}")
    with open(file_path, "r") as config_data:
        full_config = yaml.safe_load(config_data)
    return full_config


def config_logger(verbose: int):
    set_verbose_level(verbose)  # performance-critical, <4 reduces chatter during main-loop
    if verbose == 0:
        logger.setLevel(logging.ERROR)
    elif verbose == 1:
        logger.setLevel(logging.WARNING)
    elif verbose == 2:
        logger.setLevel(logging.INFO)
    elif verbose > 2:
        logger.setLevel(logging.DEBUG)
    if verbose < 3:
        # reduce log-overhead when not debugging, also more user-friendly exceptions
        logging._srcfile = None
        logging.logThreads = 0
        logging.logProcesses = 0


@click.group(context_settings=dict(help_option_names=["-h", "--help"], obj={}))
@click.option("-v", "--verbose", count=True, default=2)
@click.pass_context
def cli(ctx, verbose: int):
    """ Shepherd: Synchronized Energy Harvesting Emulator and Recorder

    Args:
        ctx:
        verbose:
    Returns:
    """
    config_logger(verbose)


@cli.command(short_help="Turns target power supply on or off (i.e. for programming)")
@click.option("--on/--off", default=True)
@click.option("--voltage", "-v", type=click.FLOAT, default=3.0, help="Target supply voltage")
@click.option("--gpio_pass/--gpio_omit", type=click.BOOL, default=True, help="Route UART, Programmer-Pins and other GPIO to this target")
@click.option("--sel_a/--sel_b", default=True,
              help="Choose (main)Target that gets connected to virtual Source")
def target_power(on: bool, voltage: float, gpio_pass: bool, sel_a: bool):
    if not on:
        voltage = 0.0
    # TODO: output would be nicer when this uses shepherdDebug as base
    for pin_name in ["en_shepherd"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(on)
        logger.info(f"Shepherd-State \t= {'enabled' if on else 'disabled'}")
    for pin_name in ["target_pwr_sel"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(not sel_a)  # switched because rail A is AUX
        logger.info(f"Select Target \t= {'A' if sel_a else 'B'}")
    for pin_name in ["target_io_sel"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(sel_a)
    for pin_name in ["target_io_en"]:
        pin = GPIO(gpio_pin_nums[pin_name], "out")
        pin.write(gpio_pass)
        logger.info(f"IO passing \t= {'enabled' if gpio_pass else 'disabled'}")
    cal = CalibrationData.from_default()
    logger.info(f"Target Voltage \t= {voltage} V")
    sysfs_interface.write_dac_aux_voltage(cal, voltage)
    sysfs_interface.write_mode("emulation", force=True)
    sysfs_interface.set_stop(force=True)  # forces reset
    logger.info(f"Re-Initialized PRU to finalize settings")
    # NOTE: this FN needs persistent IO, (old GPIO-Lib)


@cli.command(
    short_help="Runs a command with given parameters. Mainly for use with config file.")
@click.option("--command", default="record", type=click.Choice(["record", "emulate"]))
@click.option("--parameters", default={}, type=click.UNPROCESSED)
@click.option("-v", "--verbose", count=True)
@click_config_file.configuration_option(provider=yamlprovider, implicit=False)
def run(command, parameters: Dict, verbose):

    config_logger(verbose)

    if not isinstance(parameters, Dict):
        raise click.BadParameter(f"parameter-argument is not dict, but {type(parameters)} (last occurred with v8-alpha-version of click-lib)")

    # TODO: test input parameters before - crashes because of wrong parameters are ugly
    logger.info(f"CLI did process run()")
    if command == "record":
        if "output_path" in parameters:
            parameters["output_path"] = Path(parameters["output_path"])
        run_record(**parameters)
    elif command == "emulate":
        if ("output_path" in parameters) and (parameters["output_path"] is not None):
            parameters["output_path"] = Path(parameters["output_path"])
        if "input_path" in parameters:
            parameters["input_path"] = Path(parameters["input_path"])
        emu_translator = {"enable_io": "set_target_io_lvl_conv", "io_sel_target_a": "sel_target_for_io", "pwr_sel_target_a": "sel_target_for_pwr", "aux_voltage": "aux_target_voltage", "virtsource": "settings_virtsource"}
        for key, value in emu_translator.items():
            if key in parameters:
                parameters[value] = parameters[key]
                parameters.pop(key)
        run_emulate(**parameters)
    else:
        raise click.BadParameter(f"command {command} not supported")


@cli.command(short_help="Record IV data")
@click.option("--output_path", "-o", type=click.Path(), default="/var/shepherd/recordings",
              help="Dir or file path for resulting hdf5 file",)
@click.option("--mode", type=click.Choice(["harvesting", "harvesting_test"]), default="harvesting",
              help="Record 'harvesting' or 'harvesting_test'-function data")
@click.option("--harvester", type=str, default=None,
              help="Choose one of the predefined virtual harvesters")
@click.option("--duration", "-d", type=click.FLOAT, help="Duration of recording in seconds")
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option("--default-cal", is_flag=True, help="Use default calibration values")
@click.option("--start-time", "-s", type=click.FLOAT,
              help="Desired start time in unix epoch time",)
@click.option("--warn-only/--no-warn-only", default=True, help="Warn only on errors")
def record(
    output_path,
    mode,
    harvester,
    duration,
    force_overwrite,
    default_cal,
    start_time,
    warn_only,
):
    run_record(
        output_path=Path(output_path),
        mode=mode,
        harvester=harvester,
        duration=duration,
        force_overwrite=force_overwrite,
        default_cal=default_cal,
        start_time=start_time,
        warn_only=warn_only,
    )


@cli.command(
    short_help="Emulate data, where INPUT is an hdf5 file containing harvesting data"
)
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output_path", "-o", type=click.Path(),
              help="Dir or file path for storing the power consumption data")
@click.option("--duration", "-d", type=click.FLOAT, help="Duration of recording in seconds")
@click.option("--force_overwrite", "-f", is_flag=True, help="Overwrite existing file")
@click.option("--default-cal", is_flag=True, help="Use default calibration values")
@click.option("--start-time", "-s", type=click.FLOAT, help="Desired start time in unix epoch time")
@click.option("--enable_io/--disable_io", default=True,
              help="Switch the GPIO level converter to targets on/off")
@click.option("--io_sel_target_a/--io_sel_target_b", default=True,
              help="Choose Target that gets connected to IO")
@click.option("--pwr_sel_target_a/--pwr_sel_target_b", default=True,
              help="Choose (main)Target that gets connected to virtual Source")
@click.option("--aux_voltage", default=0.0,
              help="Set Voltage of auxiliary Power Source (second target). \n"
                   "- set 0-4.5 for specific const voltage, \n"
                   "- 'mid' for intermediate voltage (vsource storage cap), \n"
                   "- True or 'main' to mirror main target voltage")
@click.option("--virtsource", default="direct", help="Use the desired setting for the virtual source, provide yaml or name like BQ25570")
@click.option("--uart_baudrate", "-b", default=None, type=click.INT, help="Enable UART-Logging for target by setting a baudrate")
@click.option("--warn-only/--no-warn-only", default=True, help="Warn only on errors")
@click.option("--skip_log_voltage", is_flag=True, help="reduce file-size by omitting voltage-logging")
@click.option("--skip_log_current", is_flag=True, help="reduce file-size by omitting current-logging")
@click.option("--skip_log_gpio", is_flag=True, help="reduce file-size by omitting gpio-logging")
@click.option("--log_mid_voltage", is_flag=True, help="record / log virtual intermediate (cap-)voltage and -current (out) instead of output-voltage and -current")
def emulate(
        input_path,
        output_path,
        duration,
        force_overwrite,
        default_cal,
        start_time,
        enable_io,
        io_sel_target_a,
        pwr_sel_target_a,
        aux_voltage,
        virtsource,
        uart_baudrate,
        warn_only,
        skip_log_voltage, skip_log_current, skip_log_gpio,
        log_mid_voltage
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
        default_cal=default_cal,
        start_time=start_time,
        set_target_io_lvl_conv=enable_io,
        sel_target_for_io=io_sel_target_a,
        sel_target_for_pwr=pwr_sel_target_a,
        aux_target_voltage=aux_voltage,
        settings_virtsource=virtsource,
        log_intermediate_voltage=log_mid_voltage,
        uart_baudrate=uart_baudrate,
        warn_only=warn_only,
        skip_log_voltage=skip_log_voltage,
        skip_log_current=skip_log_current,
        skip_log_gpio=skip_log_gpio
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
@click.option("--version", "-v", type=click.STRING, default="22A0",
              help="Cape version number, 4 Char, e.g. 22A0, reflecting hardware revision")
@click.option("--serial_number", "-s", type=click.STRING,
              help="Cape serial number, 12 Char, e.g. 2021w28i0001, reflecting year, week of year, increment")
@click.option("--cal-file", "-c", type=click.Path(exists=True),
              help="YAML-formatted file with calibration data")
@click.option("--default-cal", is_flag=True, help="Use default calibration data (skip eeprom)")
def write(infofile, version, serial_number, cal_file, default_cal):
    if infofile is not None:
        if serial_number is not None or version is not None:
            raise click.UsageError(
                (
                    "--infofile and --version/--serial_number"
                    " are mutually exclusive"
                )
            )
        cape_data = CapeData.from_yaml(infofile)
        with EEPROM() as storage:
            storage.write_cape_data(cape_data)
    elif serial_number is not None or version is not None:
        if version is None or serial_number is None:
            raise click.UsageError("--version and --serial_number are required")
        cape_data = CapeData.from_values(serial_number, version)
        with EEPROM() as storage:
            storage.write_cape_data(cape_data)

    if cal_file is not None:
        if default_cal:
            raise click.UsageError("--default-cal and --cal-file are mutually exclusive")
        cal = CalibrationData.from_yaml(cal_file)
        with EEPROM() as storage:
            storage.write_calibration(cal)
    if default_cal:
        cal = CalibrationData.from_default()
        with EEPROM() as storage:
            storage.write_calibration(cal)


@eeprom.command(short_help="Read cape info and calibration data from EEPROM")
@click.option("--infofile", "-i", type=click.Path(),
              help="If provided, cape info data is dumped to this file")
@click.option("--cal-file", "-c", type=click.Path(),
              help="If provided, calibration data is dumped to this file")
def read(infofile, cal_file):

    with EEPROM() as storage:
        cape_data = storage.read_cape_data()
        cal = storage.read_calibration()

    if infofile:
        with open(infofile, "w") as f:
            f.write(repr(cape_data))
    else:
        print(repr(cape_data))

    if cal_file:
        with open(cal_file, "w") as f:
            f.write(repr(cal))
    else:
        print(repr(cal))


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
@click.option("--port", "-p", type=click.INT, default=4242)
def rpc(port):

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
def launcher(led, button):
    with Launcher(button, led) as launch:
        launch.run()


@cli.command(short_help="Program Target-Controller", context_settings={"ignore_unknown_options": True})
@click.argument("firmware-file", type=click.Path(exists=True, dir_okay=False))
@click.option("--sel_a/--sel_b", type=click.BOOL, default=True,
              help="Choose Target-Port for programming")
@click.option("--voltage", "-v", type=click.FLOAT, default=3.0, help="Target supply voltage")
@click.option("--speed", "-s", type=click.INT, default=1000, help="Programming-Datarate")
@click.option("--protocol", "-p", type=click.Choice(["swd", "sbw", "jtag"]), default="swd", help="Programming-Protocol")
def program(firmware_file, sel_a, voltage, speed, protocol):

    with ShepherdDebug(use_io=False) as sd, open(firmware_file, "rb") as fw:
        sysfs_interface.set_stop(force=True)  # create defined pru-state
        sd.set_power_state_emulator(True)
        sd.select_target_for_io_interface(sel_a=sel_a)
        sd.set_io_level_converter(True)
        sd.select_target_for_power_tracking(sel_a=not sel_a)

        cal = CalibrationData.from_default()
        sysfs_interface.write_dac_aux_voltage(cal, voltage)
        sd.shared_mem.write_firmware(fw.read())

        logger.info(f"Programming initialized, will start now")
        sysfs_interface.write_programmer_ctrl(protocol, speed, 24, 25, 26, 27)  # TODO: pins-nums are placeholders
        sysfs_interface.start_programmer()

        state = sysfs_interface.check_programmer()
        while state is not "idle":
            logger.info(f"Programming in progress, state = {state})")
            time.sleep(1)
            state = sysfs_interface.check_programmer()
        logger.info(f"Finished Programming!,    ctrl = {sysfs_interface.read_programmer_ctrl()})")


if __name__ == "__main__":
    cli()
