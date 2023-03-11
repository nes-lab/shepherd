from datetime import datetime
from pathlib import Path
from time import time
from typing import Dict
from typing import Optional

import click
import numpy as np
import yaml

from .calibrator import INSTR_4WIRE
from .calibrator import INSTR_CAL_EMU
from .calibrator import INSTR_CAL_HRV
from .calibrator import Calibrator
from .logger import logger
from .logger import set_verbose_level
from .profile_analyzer import analyze_directory
from .profiler import INSTR_PROFILE_SHP
from .profiler import Profiler


# TODO: it may be useful to move host, user and password arguments to here
@click.group(context_settings={"help_option_names": ["-h", "--help"], "obj": {}})
@click.option(
    "-v",
    "--verbose",
    count=True,
    default=3,
    help="4 Levels",
)
@click.version_option()
# @click.pass_context
def cli(verbose: int):
    set_verbose_level(verbose)


# #############################################################################
#                               Calibration
# #############################################################################


@cli.group(
    short_help="Command-Group for initializing the shepherd-cape with a Keithley SMU",
)
def calibration():
    pass


@calibration.command(
    "measure",
    short_help="Measure calibration-data from shepherd cape with Keithley SMU",
)
@click.argument("host", type=click.STRING)
@click.option("--user", "-u", type=click.STRING, default="jane", help="Host Username")
@click.option(
    "--password",
    "-p",
    type=click.STRING,
    default=None,
    help="Host User Password -> only needed when key-credentials are missing",
)
@click.option(
    "--outfile",
    "-o",
    type=click.Path(exists=False),
    help="save-file, file gets extended if it already exists",
)
@click.option(
    "--smu-ip",
    type=click.STRING,
    default="192.168.1.108",
    help="IP of SMU-Device in network",
)
@click.option("--harvester", "-h", is_flag=True, help="only handle harvester")
@click.option("--emulator", "-e", is_flag=True, help="only handle emulator")
@click.option(
    "--smu-2wire",
    is_flag=True,
    help="don't use 4wire-mode for measuring voltage (NOT recommended)",
)
@click.option(
    "--smu-nplc",
    type=click.FLOAT,
    default=16,
    help="measurement duration in pwrline cycles (.001 to 25, but > 18 can cause error-msgs)",
)
def cal_measure(
    host: str,
    user: str,
    password: str,
    outfile: Path,
    smu_ip: str,
    harvester: bool,
    emulator: bool,
    smu_2wire: bool,
    smu_nplc: float,
):
    smu_4wire = not smu_2wire
    if not any([harvester, emulator]):
        harvester = True
        emulator = True

    results = {}
    if (outfile is not None) and Path(outfile).exists():
        with open(outfile) as config_data:
            config = yaml.safe_load(config_data)
            if "measurements" in config:
                results = config["measurements"]
                logger.info("Save-File loaded successfully - will extend dataset")

    shpcal = Calibrator(host, user, password, smu_ip, smu_4wire, smu_nplc)

    if harvester:
        click.echo(INSTR_CAL_HRV)
        if not smu_4wire:
            click.echo(INSTR_4WIRE)
        usr_conf = click.confirm("Confirm that everything is set up ...", default=True)
        if usr_conf:
            results["harvester"] = shpcal.measure_harvester()

    if emulator:
        click.echo(INSTR_CAL_EMU)
        if not smu_4wire:
            click.echo(INSTR_4WIRE)
        usr_conf = click.confirm("Confirm that everything is set up ...", default=True)
        if usr_conf:
            results["emulator"] = shpcal.measure_emulator()

    out_dict = {"node": host, "measurements": results}
    res_repr = yaml.dump(out_dict, default_flow_style=False)
    logger.info(res_repr)

    if outfile is None:
        timestamp = datetime.fromtimestamp(time())
        timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        outfile = Path(f"./{timestring}_shepherd_cape_measurement.yml")
        # TODO: change suffix to .measurement.yml
        logger.debug("No filename provided -> set to '%s'.", outfile)
    with open(outfile, "w") as f:
        f.write(res_repr)
    logger.info("Saved Cal-Measurement to '%s'.", outfile)


@calibration.command("convert", short_help="Convert measurement to calibration-data")
@click.argument(
    "infile",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
)
@click.option("--outfile", "-o", type=click.Path())
@click.option(
    "--plot",
    "-p",
    is_flag=True,
    help="generate plots that contain data points and calibration model",
)
def cal_convert(infile: Path, outfile: Optional[Path], plot: bool):
    outfile = Calibrator.convert(infile, outfile, plot)
    logger.info("Cal-File was written to '%s'", outfile)


@calibration.command("write", short_help="Write calibration-data to shepherd cape")
@click.argument("host", type=click.STRING)
@click.option("--user", "-u", type=click.STRING, default="joe")
@click.option(
    "--password",
    "-p",
    type=click.STRING,
    default=None,
    help="Host User Password -> only needed when key-credentials are missing",
)
@click.option(
    "--cal_file",
    "-c",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
)
@click.option(
    "--measurement_file",
    "-m",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
)
@click.option(
    "--version",
    "-v",
    type=click.STRING,
    default="24B0",
    help="Cape version number, max 4 Char, e.g. 24B0, reflecting hardware revision",
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
def cal_write(
    host: str,
    user: str,
    password: str,
    cal_file: Path,
    measurement_file: Path,
    version: str,
    serial_number: str,
    cal_date: str,
):
    if not any([cal_file, measurement_file]):
        raise click.UsageError("provide one of cal-file or measurement-file")
    if all([cal_file, measurement_file]):
        raise click.UsageError("provide only one of cal-file or measurement-file")

    if measurement_file is not None:
        cal_file = Calibrator.convert(measurement_file)
        # TODO: change default suffix to .calibration.yml

    shpcal = Calibrator(host, user, password)
    shpcal.write(cal_file, serial_number, version, cal_date)
    shpcal.read()


@calibration.command("read", short_help="Read calibration-data from shepherd cape")
@click.argument("host", type=click.STRING)
@click.option("--user", "-u", type=click.STRING, default="jane")
@click.option(
    "--password",
    "-p",
    type=click.STRING,
    default=None,
    help="Host User Password -> only needed when key-credentials are missing",
)
def cal_read(host: str, user: str, password: str):
    shpcal = Calibrator(host, user, password)
    shpcal.read()


# #############################################################################
#                               Profiler
# #############################################################################


@cli.group(short_help="Command-Group for profiling the analog frontends")
def profile():
    pass


@profile.command(
    "measure",
    short_help="Measure profile-data from shepherd cape with Keithley SMU",
)
@click.argument("host", type=click.STRING)
@click.option("--user", "-u", type=click.STRING, default="joe", help="Host Username")
@click.option(
    "--password",
    "-p",
    type=click.STRING,
    default=None,
    help="Host User Password -> only needed when key-credentials are missing",
)
@click.option(
    "--outfile",
    "-o",
    type=click.Path(),
    help="save file, if no filename is provided the hostname will be used",
)
@click.option(
    "--smu-ip",
    type=click.STRING,
    default="192.168.1.108",
    help="IP of SMU-Device in network",
)
@click.option(
    "--smu-2wire",
    is_flag=True,
    help="don't use 4wire-mode for measuring voltage (NOT recommended)",
)
@click.option(
    "--smu-nplc",
    type=click.FLOAT,
    default=16,
    help="measurement duration in pwrline cycles (.001 to 25, but > 18 can cause error-msgs)",
)
@click.option("--harvester", "-h", is_flag=True, help="only handle harvester")
@click.option("--emulator", "-e", is_flag=True, help="only handle emulator")
@click.option(
    "--short",
    "-s",
    is_flag=True,
    help="reduce voltage / current steps for faster profiling (2x faster)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="remove user-interaction (setup prompt)",
)
def profile_measure(
    host: str,
    user: str,
    password: str,
    outfile: Path,
    smu_ip: str,
    smu_2wire: bool,
    smu_nplc: float,
    harvester: bool,
    emulator: bool,
    short: bool,
    quiet: bool,
):
    if not any([harvester, emulator]):
        harvester = True
        emulator = True

    smu_4wire = not smu_2wire
    time_now = time()
    components = ("_emu" if emulator else "") + ("_hrv" if harvester else "")
    if outfile is None:
        timestamp = datetime.fromtimestamp(time_now)
        timestring = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        outfile = Path(f"./{timestring}_shepherd_cape")
    if short:
        file_path = outfile.stem + "_profile_short" + components + ".npz"
    else:
        file_path = outfile.stem + "_profile_full" + components + ".npz"

    shpcal = Calibrator(host, user, password, smu_ip, smu_4wire, smu_nplc)
    profiler = Profiler(shpcal, short)
    # results_hrv = results_emu_a = results_emu_b = None. TODO: check function, replaced by dict
    results: Dict[str, np.ndarray] = {}

    if not quiet:
        click.echo(INSTR_PROFILE_SHP)
        if not smu_4wire:
            click.echo(INSTR_4WIRE)
        logger.info(
            " -> Profiler will sweep through %d voltages and %d currents",
            len(profiler.voltages_V),
            len(profiler.currents_A),
        )
        click.confirm("Confirm that everything is set up ...", default=True)

    if harvester:
        results["hrv"] = profiler.measure_harvester()
    if emulator:
        results["emu_a"] = profiler.measure_emulator_a()
        results["emu_b"] = profiler.measure_emulator_b()

    np.savez_compressed(
        file_path,
        **results,
    )
    logger.info("Data was written to '%s'", file_path)
    logger.debug("Profiling took %.1f s", time() - time_now)


@profile.command("analyze", short_help="Analyze profile-data")
@click.argument(
    "infile",
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=True),
)
@click.option(
    "--outfile",
    "-o",
    type=click.Path(),
    help="CSV-File for storing meta-data of each profile (will be extended if existing)",
)
@click.option(
    "--plot",
    "-p",
    is_flag=True,
    help="generate plots that visualize the profile",
)
def profile_analyze(infile: Path, outfile: Path, plot: bool):
    """

    Args:
        infile: file or directory to
        outfile: metadata stats from files
        plot: do generate profile plots
    """
    analyze_directory(infile, outfile, plot)


if __name__ == "__main__":
    cli()
