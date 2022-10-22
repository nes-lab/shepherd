import contextlib
import logging
import threading
from io import StringIO
from pathlib import Path
from typing import List

import numpy as np
import yaml
from fabric import Group

consoleHandler = logging.StreamHandler()
logger = logging.getLogger("shepherd-herd")
logger.addHandler(consoleHandler)
# Note: defined here to avoid circular import


def set_verbose_level(verbose: int = 2) -> None:
    if verbose == 0:
        logger.setLevel(logging.ERROR)
    elif verbose == 1:
        logger.setLevel(logging.WARNING)
    elif verbose == 2:
        logger.setLevel(logging.INFO)
    elif verbose > 2:
        logger.setLevel(logging.DEBUG)


def assemble_group(
    inventory: str = "",
    limit: str = "",
    user=None,
    key_filename=None,
) -> (Group, list):

    if limit.rstrip().endswith(","):
        limit = limit.split(",")[:-1]
    else:
        limit = None

    if inventory.rstrip().endswith(","):
        hostlist = inventory.split(",")[:-1]
        if limit is not None:
            hostlist = list(set(hostlist) & set(limit))
        hostnames = {hostname: hostname for hostname in hostlist}

    else:
        # look at all these directories for inventory-file
        if inventory == "":
            inventories = [
                "/etc/shepherd/herd.yml",
                "~/herd.yml",
                "inventory/herd.yml",
            ]
        else:
            inventories = [inventory]
        host_path = None
        for inventory in inventories:
            if Path(inventory).exists():
                host_path = Path(inventory)

        if host_path is None:
            raise FileNotFoundError(", ".join(inventories))

        with open(host_path) as stream:
            try:
                inventory_data = yaml.safe_load(stream)
            except yaml.YAMLError:
                raise FileNotFoundError(f"Couldn't read inventory file {host_path}")

        hostlist = []
        hostnames = {}
        for hostname, hostvars in inventory_data["sheep"]["hosts"].items():
            if isinstance(limit, List) and (hostname not in limit):
                continue

            if "ansible_host" in hostvars:
                hostlist.append(hostvars["ansible_host"])
                hostnames[hostvars["ansible_host"]] = hostname
            else:
                hostlist.append(hostname)
                hostnames[hostname] = hostname

        if user is None:
            with contextlib.suppress(KeyError):
                user = inventory_data["sheep"]["vars"]["ansible_user"]

    if user is None:
        raise ValueError("Provide user by command line or in inventory file")

    if len(hostlist) < 1 or len(hostnames) < 1:
        raise ValueError(
            "Provide remote hosts (either inventory empty or limit does not match)"
        )

    connect_kwargs = {}
    if key_filename is not None:
        connect_kwargs["key_filename"] = key_filename
    group = Group(*hostlist, user=user, connect_kwargs=connect_kwargs)

    return group, hostnames


def thread_run(cnx, sudo: bool, cmd: str, results: np.ndarray, index: int) -> None:
    if sudo:
        results[index] = cnx.sudo(cmd, warn=True, hide=True)
    else:
        results[index] = cnx.run(cmd, warn=True, hide=True)


def group_run(group: Group, sudo: bool, cmd: str) -> np.ndarray:
    results = np.empty(len(group))
    threads = np.empty(len(group))
    for i, cnx in enumerate(group):
        threads[i] = threading.Thread(
            target=thread_run,
            args=(cnx, sudo, cmd, results, i),
            daemon=True,
        )
        threads[i].start()
    for i, _cnx in enumerate(group):
        threads[i].join()
    return results


def find_consensus_time(group: Group) -> (int, float):
    """Finds a start time in the future when all nodes should start service

    In order to run synchronously, all nodes should start at the same time.
    This is achieved by querying all nodes to check any large time offset,
    agreeing on a common time in the future and waiting for that time on each
    node.

    Args:
        group (fabric.Group): Group of fabric hosts on which to start shepherd.
    """
    # Get the current time on each target node
    ts_nows = group_run(group, sudo=False, cmd="date +%s")

    if len(ts_nows) == 1:
        ts_start = ts_nows[0] + 20
    else:
        ts_max = max(ts_nows)
        # Check for excessive time difference among nodes
        ts_diffs = ts_nows - ts_max
        if any(abs(ts_diffs) > 10):
            raise Exception("Time difference between hosts greater 10s")

        # We need to estimate a future point in time such that all nodes are ready
        ts_start = ts_max + 20 + 2 * len(group)
    return int(ts_start), float(ts_start - ts_nows[0])


def configure_sheep(
    group: Group,
    mode: str,
    parameters: dict,
    hostnames: dict,
    verbose: int = 0,
) -> None:
    """Configures shepherd service on the group of hosts.

    Rolls out a configuration file according to the given command and parameters
    service.

    Args:
        group (fabric.Group): Group of fabric hosts on which to start shepherd.
        mode (str): What shepherd is supposed to do. One of 'harvester' or 'emulator'.
        parameters (dict): Parameters for shepherd-sheep
        hostnames (dict): Dictionary of hostnames corresponding to fabric hosts
        verbose (int): Verbosity for shepherd-sheep
    """
    config_dict = {
        "mode": mode,
        "verbose": verbose,
        "parameters": parameters,
    }
    config_yml = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

    logger.debug("Rolling out the following config:\n\n%s", config_yml)

    reply = group_run(group, sudo=True, cmd="systemctl status shepherd")

    for i, cnx in group:
        if reply[i].exited != 3:
            raise Exception(f"shepherd not inactive on {hostnames[cnx.host]}")
        cnx.put(StringIO(config_yml), "/tmp/config.yml")  # noqa: S108

    group_run(group, sudo=True, cmd="mv /tmp/config.yml /etc/shepherd/config.yml")


def check_sheep(group: Group, hostnames: dict, warn: bool = False) -> bool:
    """Returns true ss long as one instance is still measuring

    :param group:
    :param hostnames:
    :param warn:
    :return: True is one node is still running
    """
    reply = group_run(group, sudo=True, cmd="systemctl status shepherd")
    running = False

    for i, cnx in group:
        if reply[i].exited != 3:
            running = True
            if warn:
                logger.warning("shepherd still active on %s", hostnames[cnx.host])
            else:
                logger.debug("shepherd still active on %s", hostnames[cnx.host])
    return running


def start_sheep(
    group: Group,
    hostnames: dict,
) -> None:
    """Starts shepherd service on the group of hosts.

    Args:
        group (fabric.Group): Group of fabric hosts on which to start shepherd.
        hostnames (dict): Dictionary of hostnames corresponding to fabric hosts
    """
    running = check_sheep(group, hostnames, warn=True)
    if running:
        logger.info("-> won't start while instances are running")
    else:
        group_run(group, sudo=True, cmd="systemctl start shepherd")


def stop_sheep(group: Group, hostnames: dict) -> bool:
    logger.debug(f"Shepherd-nodes affected: {hostnames}")
    group_run(group, sudo=True, cmd="systemctl stop shepherd")
    logger.info("Shepherd was forcefully stopped.")
    return True


def poweroff_sheep(group: Group, hostnames: dict, restart: bool) -> None:
    logger.debug(f"Shepherd-nodes affected: {hostnames}")
    if restart:
        group_run(group, sudo=True, cmd="reboot")
        logger.info("Command for rebooting nodes was issued")
    else:
        group_run(group, sudo=True, cmd="poweroff")
        logger.info("Command for powering off nodes was issued")
