from datetime import datetime
from pathlib import Path
from time import time
from typing import Optional

import click
import typer
from shepherd_core.data_models.base.cal_measurement import CalMeasurementCape
from shepherd_core.data_models.base.calibration import CapeData

from . import plot_calibration
from .calibrator import INSTR_4WIRE
from .calibrator import INSTR_CAL_EMU
from .calibrator import INSTR_CAL_HRV
from .calibrator import Calibrator
from .cli_helper import cli_setup_callback
from .cli_helper import emu_opt_t
from .cli_helper import host_arg_t
from .cli_helper import hrv_opt_t
from .cli_helper import ifile_opt_t
from .cli_helper import ofile_opt_t
from .cli_helper import pass_opt_t
from .cli_helper import smu_2w_opt_t
from .cli_helper import smu_ip_opt_t
from .cli_helper import smu_nc_opt_t
from .cli_helper import user_opt_t
from .cli_helper import verbose_opt_t
from .logger import logger

cli_cal = typer.Typer(
    name="calibration",
    help="Sub-Commands to (re-)initialize the shepherd-cape",
)

serial_opt_t = typer.Option(
    default=...,
    help="Cape serial number, max 12 Char, e.g. HRV_EMU_1001, reflecting capability & increment",
)
version_opt_t = typer.Option(
    None,
    help="Cape version number, max 4 Char, e.g. 24B0, reflecting hardware revision",
)


@cli_cal.command()
def measure(
    host: str = host_arg_t,
    user: str = user_opt_t,
    password: Optional[str] = pass_opt_t,
    outfile: Optional[Path] = ofile_opt_t,
    smu_ip: str = smu_ip_opt_t,
    smu_2wire: bool = smu_2w_opt_t,
    smu_nplc: float = smu_nc_opt_t,
    harvester: bool = hrv_opt_t,
    emulator: bool = emu_opt_t,
    cape_serial: str = serial_opt_t,
    version: Optional[str] = version_opt_t,
    verbose: bool = verbose_opt_t,
):
    """Measure calibration-data for shepherd cape"""
    cli_setup_callback(verbose)
    smu_4wire = not smu_2wire
    if not any([harvester, emulator]):
        harvester = True
        emulator = True

    if version is None:
        cape = CapeData(serial_number=cape_serial)
    else:
        cape = CapeData(serial_number=cape_serial, version=version)

    results = {"host": host, "cape": cape}

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

    msr_cape = CalMeasurementCape(**results)
    logger.info(msr_cape.model_dump())

    if outfile is None:
        timestamp = datetime.fromtimestamp(time())
        timestring = timestamp.strftime("%Y-%m-%d_%H-%M")
        outfile = Path(f"./{timestring}_shepherd_cape_{cape_serial}.measurement.yaml")
        logger.debug("No filename provided -> set to '%s'.", outfile)
    msr_cape.to_file(outfile)
    logger.info("Saved Cal-Measurement to '%s'.", outfile)

    outfile = outfile.with_stem(".".join(outfile.stem.split(".")[0:-1]) + ".cal_data")
    cal_cape = msr_cape.to_cal()
    cal_cape.to_file(outfile)
    logger.info("Saved Cal-Data to '%s'.", outfile)

    outfile = outfile.with_stem(".".join(outfile.stem.split(".")[0:-1]))
    plot_calibration(msr_cape, cal_cape, outfile)
    logger.info("Plotted Data to '%s'.", outfile)


@cli_cal.command()
def write(
    host: str = host_arg_t,
    user: str = user_opt_t,
    password: Optional[str] = pass_opt_t,
    cal_file: Optional[Path] = ifile_opt_t,
    measurement_file: Optional[Path] = ifile_opt_t,
    verbose: bool = verbose_opt_t,
):
    """Write calibration-data to shepherd cape eeprom (choose cal- or measurement-file)"""
    cli_setup_callback(verbose)
    if not any([cal_file, measurement_file]):
        raise click.UsageError("provide one of cal-file or measurement-file")
    if all([cal_file, measurement_file]):
        raise click.UsageError("provide only one of cal-file or measurement-file")

    if measurement_file is not None:
        msr_cape = CalMeasurementCape.from_file(measurement_file)
        cal_cape = msr_cape.to_cal()
        cal_file = measurement_file.with_stem(
            ".".join(measurement_file.stem.split(".")[0:-1]) + ".cal_data",
        )
        cal_cape.to_file(cal_file)

    shp_cal = Calibrator(host, user, password)
    shp_cal.write(cal_file)
    shp_cal.read()


@cli_cal.command()
def read(
    host: str = host_arg_t,
    user: str = user_opt_t,
    password: Optional[str] = pass_opt_t,
    cal_file: Optional[Path] = ofile_opt_t,
    verbose: bool = verbose_opt_t,
):
    """Read calibration-data from shepherd cape"""
    cli_setup_callback(verbose)
    shpcal = Calibrator(host, user, password)
    if cal_file is None:
        shpcal.read()
    else:
        cal_file = Path(cal_file)
        shpcal.retrieve(cal_file)
