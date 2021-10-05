import logging
import click
from shepherd.cli import consoleHandler

logger = logging.getLogger("shepherd")
logger.addHandler(consoleHandler)


def generate_rec_data():
    print("None")


@click.command()
@click.option("--duration", "-d", type=float, default=180, help="Duration of recording in seconds")
def cli(duration):
    logging._srcfile = None
    logging.logThreads = 0
    logging.logProcesses = 0


if __name__ == "__main__":
    cli()
