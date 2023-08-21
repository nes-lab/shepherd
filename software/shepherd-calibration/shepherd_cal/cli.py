import typer

from .calibrator_cli import cli_cal
from .profiler_cli import cli_pro

cli = typer.Typer(help="Qualify Shepherd-Capes with a host-sheep & Keithley SMU")
cli.add_typer(cli_cal)
cli.add_typer(cli_pro)


if __name__ == "__main__":
    cli()
