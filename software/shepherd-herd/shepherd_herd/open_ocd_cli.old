import sys
import telnetlib  # noqa: S401
import time
from pathlib import Path
from typing import Optional

import click
import typer

from .herd import Herd
from .herd_cli import cli_setup_callback
from .herd_cli import invent_opt_t
from .herd_cli import key_opt_t
from .herd_cli import limit_opt_t
from .herd_cli import user_opt_t
from .herd_cli import verbose_opt_t
from .herd_cli import version_opt_t
from .logger import logger as log

# #############################################################################
#                               OpenOCD Programmer
# #############################################################################

cli_ocd = typer.Typer(
    name="openocd",
    help="Sub-commands for (deprecated) remote programming/debugging of the target sensor node",
)
# cli.add_typer(cli_ocd)  # noqa: E800

port_opt_t = typer.Option(
    4444,
    "--port",
    "-p",
    help="Port on which OpenOCD should listen for telnet",
)
volt_opt_t = typer.Option(3.0, "--voltage", "-v", help="Target supply voltage")
tgtp_opt_t = typer.Option(
    "A",
    "--target-port",
    "-t",
    click_type=click.Choice(["A", "B"]),
    help="Choose Target-Port of Cape for programming",
)

image_arg_t = typer.Argument(
    ...,
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
)


def openocd_prepare(
    herd: Herd,
    voltage: float,
    target_port: str,
    timeout: float = 30,
) -> None:
    target_port = target_port.upper()
    if target_port not in ["A", "B"]:
        raise ValueError("Target-Port has to be A or B, but was '%s'", target_port)
    herd.run_cmd(sudo=True, cmd="systemctl start shepherd-openocd")
    herd.run_cmd(
        sudo=True,
        cmd=f"shepherd-sheep -vvv "
        f"target-power --on --voltage {voltage} --target-port {target_port}",
    )
    ts_end = time.time() + timeout
    while True:
        openocd_status = herd.run_cmd(
            sudo=True,
            cmd="systemctl status shepherd-openocd",
        )
        exit_code = max([reply.exited for reply in openocd_status.values()])
        exit_nodes = [
            key for key, value in openocd_status.items() if value.exited == exit_code
        ]
        if exit_code == 0:
            break
        if time.time() > ts_end:
            raise TimeoutError(f"Timed out waiting for openocd on hosts {exit_nodes}")
        else:
            log.debug("waiting for openocd on %s", exit_nodes)
            time.sleep(1)


def openocd_finish(herd: Herd) -> None:
    replies1 = herd.run_cmd(
        sudo=True,
        cmd="systemctl stop shepherd-openocd",
    )
    replies2 = herd.run_cmd(
        sudo=True,
        cmd="shepherd-sheep -vvv target-power --off",
    )
    exit_code = max(
        [reply.exited for reply in replies1.values()]
        + [reply.exited for reply in replies2.values()],
    )
    sys.exit(exit_code)


@cli_ocd.command(help="Flashes the binary IMAGE file to the target")
def flash(
    image: Path = image_arg_t,
    # openocd-related params
    port: int = port_opt_t,
    voltage: float = volt_opt_t,
    target_port: str = tgtp_opt_t,
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
    openocd_prepare(herd, voltage, target_port)
    for cnx in herd.group:
        hostname = herd.hostnames[cnx.host]
        cnx.put(image, "/tmp/target_image.bin")  # noqa: S108
        with telnetlib.Telnet(cnx.host, port) as tn:
            log.debug("connected to openocd on %s", hostname)
            tn.write(b"program /tmp/target_image.bin verify reset\n")
            res = tn.read_until(b"Verified OK", timeout=5)
            if b"Verified OK" in res:
                log.info("flashed image on %s successfully", hostname)
            else:
                log.error("failed flashing image on %s", hostname)
    openocd_finish(herd)


@cli_ocd.command(help="Halts the target")
def halt(
    # openocd-related params
    port: int = port_opt_t,
    voltage: float = volt_opt_t,
    target_port: str = tgtp_opt_t,
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
    openocd_prepare(herd, voltage, target_port)
    for cnx in herd.group:
        hostname = herd.hostnames[cnx.host]
        with telnetlib.Telnet(cnx.host, port) as tn:
            log.debug("connected to openocd on %s", hostname)
            tn.write(b"halt\n")
            log.info("target halted on %s", hostname)
    openocd_finish(herd)


@cli_ocd.command(help="Erases the target")
def erase(
    # openocd-related params
    port: int = port_opt_t,
    voltage: float = volt_opt_t,
    target_port: str = tgtp_opt_t,
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
    openocd_prepare(herd, voltage, target_port)
    for cnx in herd.group:
        hostname = herd.hostnames[cnx.host]
        with telnetlib.Telnet(cnx.host, port) as tn:
            log.debug("connected to openocd on %s", hostname)
            tn.write(b"halt\n")
            log.info("target halted on %s", hostname)
            tn.write(b"nrf52 mass_erase\n")
            log.info("target erased on %s", hostname)
    openocd_finish(herd)


@cli_ocd.command(help="Resets the target")
def reset(
    # openocd-related params
    port: int = port_opt_t,
    voltage: float = volt_opt_t,
    target_port: str = tgtp_opt_t,
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
    openocd_prepare(herd, voltage, target_port)
    for cnx in herd.group:
        hostname = herd.hostnames[cnx.host]
        with telnetlib.Telnet(cnx.host, port) as tn:
            log.debug("connected to openocd on %s", hostname)
            tn.write(b"reset\n")
            log.info("target reset on %s", hostname)
    openocd_finish(herd)
