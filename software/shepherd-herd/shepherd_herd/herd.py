"""
Herd-Baseclass
"""
import contextlib
import logging
import threading
import time
from io import StringIO
from pathlib import Path
from typing import List

import numpy as np
import yaml
from fabric import Group

consoleHandler = logging.StreamHandler()
logger = logging.getLogger("shepherd-herd")
logger.addHandler(consoleHandler)
verbose_level = 0
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
    global verbose_level
    verbose_level = verbose


class Herd:

    group: Group = None
    hostnames: dict = None

    _remote_paths_allowed = [
        Path("/var/shepherd/recordings/"),  # default
        Path("/var/shepherd/"),
        Path("/etc/shepherd/"),
        Path("/tmp/"),  # noqa: S108
    ]
    path_default = _remote_paths_allowed[0]

    def __init__(
        self,
        inventory: str = "",
        limit: str = "",
        user=None,
        key_filename=None,
    ):

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

        self.group = Group(*hostlist, user=user, connect_kwargs=connect_kwargs)
        self.hostnames = hostnames

    def __getitem__(self, key):
        if key in self.hostnames:
            return self.hostnames[key]
        raise KeyError

    def __repr__(self):
        return self.hostnames

    @staticmethod
    def thread_run(cnx, sudo: bool, cmd: str, results: np.ndarray, index: int) -> None:
        if sudo:
            results[index] = cnx.sudo(cmd, warn=True, hide=True)
        else:
            results[index] = cnx.run(cmd, warn=True, hide=True)

    def run_cmd(self, sudo: bool, cmd: str) -> np.ndarray:
        results = np.empty(len(self.group))
        threads = np.empty(len(self.group))
        for i, cnx in enumerate(self.group):
            threads[i] = threading.Thread(
                target=self.thread_run,
                args=(cnx, sudo, cmd, results, i),
                daemon=True,
            )
            threads[i].start()
        for i, _cnx in enumerate(self.group):
            threads[i].join()
        return results

    @staticmethod
    def thread_put(cnx, src: [Path, str], dst: [Path, str], force_overwrite: bool):
        tmp_path = Path("/tmp") / dst.name  # noqa: S108
        xtr_arg = "-f" if force_overwrite else "-n"

        cnx.put(str(src), str(tmp_path))  # noqa: S108
        cnx.sudo(f"mv {xtr_arg} {tmp_path} {dst}", warn=True, hide=True)

    def put_file(
        self, src: [Path, str], dst: [Path, str], force_overwrite: bool
    ) -> None:

        src_path = Path(src).absolute()
        if not src_path.exists():
            raise FileNotFoundError("Local source file '%s' does not exist!", src_path)
        logger.info("Local source path = %s", src_path)

        if dst is None:
            remote_path = self.path_default
            logger.debug("Remote path not provided -> default = %s", remote_path)
        else:
            remote_path = Path(dst).absolute()
            is_allowed = False
            for path_allowed in self._remote_paths_allowed:
                if str(remote_path).startswith(str(path_allowed)):
                    is_allowed = True
            if is_allowed:
                logger.info("Remote path = %s", remote_path)
            else:
                raise NameError(f"provided path was forbidden ('{remote_path}')")

        threads = np.empty(len(self.group))
        for i, cnx in enumerate(self.group):
            threads[i] = threading.Thread(
                target=self.thread_put,
                args=(cnx, src, dst, force_overwrite),
                daemon=True,
            )
            threads[i].start()
        for i, _cnx in enumerate(self.group):
            threads[i].join()

    def get_file(
        self,
        src: [Path, str],
        dst_dir: [Path, str],
        timestamp: bool = False,
        separate: bool = False,
        delete_src: bool = False,
    ) -> bool:
        time_str = time.strftime("%Y_%m_%dT%H_%M_%S")
        xtra_ts = f"_{time_str}" if timestamp else ""
        failed_retrieval = False

        threads = np.empty(len(self.group))
        dst_paths = np.empty(len(self.group))

        # assemble file-names
        if Path(src).is_absolute():
            src_path = Path(src)
        else:
            src_path = Path(self.path_default) / src

        for i, cnx in enumerate(self.group):
            hostname = self.hostnames[cnx.host]
            if separate:
                target_path = Path(dst_dir) / hostname
                xtra_node = ""
            else:
                target_path = Path(dst_dir)
                xtra_node = f"_{hostname}"

            dst_paths[i] = target_path / (
                str(src_path.stem) + xtra_ts + xtra_node + src_path.suffix
            )

        # check if file is present
        reply = self.run_cmd(sudo=False, cmd=f"test -f {src_path}")

        # try to fetch data
        for i, cnx in enumerate(self.group):
            hostname = self.hostnames[cnx.host]
            if reply[i].exited > 0:
                logger.error(
                    "remote file '%s' does not exist on node %s",
                    src_path,
                    hostname,
                )
                failed_retrieval = True
                continue

            dst_path = dst_paths[i].parent
            if not dst_path.exists():
                logger.info("creating local dir %s", dst_path)
                dst_path.mkdir()

            logger.debug(
                "retrieving remote file '%s' from %s to local '%s'",
                src_path,
                hostname,
                dst_path,
            )

            threads[i] = threading.Thread(
                target=cnx.get,
                args=(src_path, dst_path),
                daemon=True,
            )
            threads[i].start()

        for i, cnx in enumerate(self.group):
            hostname = self.hostnames[cnx.host]
            if reply[i].exited > 0:
                continue
            threads[i].join()
            if delete_src:
                logger.info(
                    "deleting %s from remote %s",
                    src_path,
                    hostname,
                )
                cnx.sudo(f"rm {src_path}", hide=True)

        return failed_retrieval

    def find_consensus_time(self) -> (int, float):
        """Finds a start time in the future when all nodes should start service

        In order to run synchronously, all nodes should start at the same time.
        This is achieved by querying all nodes to check any large time offset,
        agreeing on a common time in the future and waiting for that time on each
        node.
        """
        # Get the current time on each target node
        ts_nows = self.run_cmd(sudo=False, cmd="date +%s")

        if len(ts_nows) == 1:
            ts_start = ts_nows[0] + 20
        else:
            ts_max = max(ts_nows)
            # Check for excessive time difference among nodes
            ts_diffs = ts_nows - ts_max
            if any(abs(ts_diffs) > 10):
                raise Exception("Time difference between hosts greater 10s")

            # We need to estimate a future point in time such that all nodes are ready
            ts_start = ts_max + 20 + 2 * len(self.group)
        return int(ts_start), float(ts_start - ts_nows[0])

    def configure_measurement(
        self,
        mode: str,
        parameters: dict,
    ) -> None:
        """Configures shepherd service on the group of hosts.

        Rolls out a configuration file according to the given command and parameters
        service.

        Args:
            mode (str): What shepherd is supposed to do. One of 'harvester' or 'emulator'.
            parameters (dict): Parameters for shepherd-sheep
        """
        global verbose_level
        config_dict = {
            "mode": mode,
            "verbose": verbose_level,
            "parameters": parameters,
        }
        config_yml = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

        logger.debug("Rolling out the following config:\n\n%s", config_yml)

        reply = self.run_cmd(sudo=True, cmd="systemctl status shepherd")
        for i, cnx in self.group:
            if reply[i].exited != 3:
                raise Exception(f"shepherd not inactive on {self.hostnames[cnx.host]}")

        self.put_file(
            StringIO(config_yml), "/etc/shepherd/config.yml", force_overwrite=True
        )

    def check_state(self, warn: bool = False) -> bool:
        """Returns true ss long as one instance is still measuring

        :param warn:
        :return: True is one node is still running
        """
        reply = self.run_cmd(sudo=True, cmd="systemctl status shepherd")
        running = False

        for i, cnx in self.group:
            if reply[i].exited != 3:
                running = True
                if warn:
                    logger.warning(
                        "shepherd still active on %s", self.hostnames[cnx.host]
                    )
                else:
                    logger.debug(
                        "shepherd still active on %s", self.hostnames[cnx.host]
                    )
        return running

    def start_measurement(self) -> None:
        """Starts shepherd service on the group of hosts."""
        running = self.check_state(warn=True)
        if running:
            logger.info("-> won't start while instances are running")
        else:
            self.run_cmd(sudo=True, cmd="systemctl start shepherd")

    def stop_measurement(self) -> bool:
        logger.debug("Shepherd-nodes affected: %s", self.hostnames)
        self.run_cmd(sudo=True, cmd="systemctl stop shepherd")
        logger.info("Shepherd was forcefully stopped.")
        return True

    def poweroff(self, restart: bool) -> None:
        logger.debug("Shepherd-nodes affected: %s", self.hostnames)
        if restart:
            self.run_cmd(sudo=True, cmd="reboot")
            logger.info("Command for rebooting nodes was issued")
        else:
            self.run_cmd(sudo=True, cmd="poweroff")
            logger.info("Command for powering off nodes was issued")

    def await_stop(self, timeout: int = 30) -> bool:
        ts_end = time.time() + timeout
        while self.check_state():
            if time.time() > ts_end:
                return self.check_state(warn=True)
            time.sleep(1)
        return False
