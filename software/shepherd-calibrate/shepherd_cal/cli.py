from pathlib import Path

import click
import yaml
from .calibrate import set_verbose_level
from .calibrate import logger, Cal, INSTR_HRVST, INSTR_4WIRE, INSTR_EMU


@click.group(context_settings={"help_option_names": ["-h", "--help"], "obj": {}})
@click.option("-v", "--verbose", count=True, default=3)
def cli(verbose):
    set_verbose_level(verbose)


@cli.command()
@click.argument("host", type=str)
@click.option("--user", "-u", type=str, default="jane", help="Host Username")
@click.option(
    "--password",
    "-p",
    type=str,
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
    "--smu-ip", type=str, default="192.168.1.108", help="IP of SMU-Device in network"
)
@click.option("--all", "all_", is_flag=True, help="handle both, harvester and emulator")
@click.option("--harvester", "-h", is_flag=True, help="handle only harvester")
@click.option("--emulator", "-e", is_flag=True, help="handle only emulator")
@click.option(
    "--smu-4wire",
    is_flag=True,
    help="use 4wire-mode for measuring voltage (recommended)",
)
@click.option(
    "--smu-nplc",
    type=float,
    default=16,
    help="measurement duration in pwrline cycles (.001 to 25, but > 18 can cause error-msgs)",
)
def measure(
    host,
    user,
    password,
    outfile,
    smu_ip,
    all_,
    harvester,
    emulator,
    smu_4wire,
    smu_nplc,
):

    if all_:
        if harvester or emulator:
            raise click.UsageError("Either provide --all or individual flags")

        harvester = True
        emulator = True
    if not any([all_, harvester, emulator]):
        harvester = True
        emulator = True

    results = {}
    if (outfile is not None) and Path(outfile).exists():
        with open(outfile) as config_data:
            config = yaml.safe_load(config_data)
            if "measurements" in config:
                results = config["measurements"]
                logger.info("Save-File loaded successfully - will extend dataset")

    shpcal = Cal(host, user, password, smu_ip, smu_4wire, smu_nplc)

    if harvester:
        click.echo(INSTR_HRVST)
        if not smu_4wire:
            click.echo(INSTR_4WIRE)
        usr_conf = click.confirm("Confirm that everything is set up ...")
        if usr_conf:
            results["harvester"] = shpcal.measure_harvester()

    if emulator:
        click.echo(INSTR_EMU)
        if not smu_4wire:
            click.echo(INSTR_4WIRE)
        usr_conf = click.confirm("Confirm that everything is set up ...")
        if usr_conf:
            results["emulator"] = shpcal.measure_emulator()

    out_dict = {"node": host, "measurements": results}
    res_repr = yaml.dump(out_dict, default_flow_style=False)
    if outfile is not None:
        with open(outfile, "w") as f:
            f.write(res_repr)
    else:
        logger.info(res_repr)


@cli.command()
@click.argument("infile", type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False))
@click.option("--outfile", "-o", type=click.Path())
@click.option(
    "--plot",
    "-p",
    is_flag=True,
    help="generate plots that contain data points and calibration model",
)
def convert(infile, outfile, plot: bool):
    Cal.convert(infile, outfile, plot)


@cli.command()
@click.argument("host", type=str)
@click.option("--user", "-u", type=str, default="joe")
@click.option(
    "--password",
    "-p",
    type=str,
    default=None,
    help="Host User Password -> only needed when key-credentials are missing",
)
@click.option("--cal_file", "-c", type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False))
@click.option("--measurement_file", "-m", type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False))
@click.option(
    "--version",
    "-v",
    type=click.STRING,
    default="24A0",
    help="Cape version number, max 4 Char, e.g. 22A0, reflecting hardware revision",
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
def write(host, user, password, cal_file, measurement_file, version, serial_number, cal_date):

    if cal_file is None:
        if measurement_file is None:
            raise click.UsageError("provide one of cal-file or measurement-file")
        cal_file = Cal.convert(measurement_file)
    else:
        if measurement_file is not None:
            raise click.UsageError("provide only one of cal-file or measurement-file")

    shpcal = Cal(host, user, password)
    shpcal.write(cal_file, serial_number, version, cal_date)
    shpcal.read()


@cli.command()
@click.argument("host", type=str)
@click.option("--user", "-u", type=str, default="jane")
@click.option(
    "--password",
    "-p",
    type=str,
    default=None,
    help="Host User Password -> only needed when key-credentials are missing",
)
def read(host, user, password):
    shpcal = Cal(host, user, password)
    shpcal.read()


if __name__ == "__main__":
    cli()
