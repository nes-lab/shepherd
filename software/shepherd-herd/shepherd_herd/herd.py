"""Herd-Baseclass for controlling the sheep-observer-nodes."""

import contextlib
import logging
import threading
import time
from datetime import datetime
from datetime import timedelta
from io import StringIO
from pathlib import Path
from pathlib import PurePath
from pathlib import PurePosixPath
from types import TracebackType
from typing import Any
from typing import ClassVar

import yaml
from fabric import Connection
from fabric import Group
from fabric import Result
from paramiko.ssh_exception import NoValidConnectionsError
from paramiko.ssh_exception import SSHException
from pydantic import validate_call
from shepherd_core import Inventory
from shepherd_core import local_tz
from shepherd_core.data_models import ShpModel
from shepherd_core.data_models import Wrapper
from shepherd_core.data_models.task import extract_tasks
from shepherd_core.data_models.task import prepare_task
from shepherd_core.data_models.testbed import Testbed
from shepherd_core.testbed_client import tb_client
from tqdm import tqdm
from typing_extensions import Self

from .logger import logger


class Herd:
    path_default = PurePosixPath("/var/shepherd/recordings/")
    _remote_paths_allowed: ClassVar[set] = {
        path_default,  # default
        PurePosixPath("/var/shepherd/"),
        PurePosixPath("/etc/shepherd/"),
        PurePosixPath("/tmp/"),  # noqa: S108
    }

    timestamp_diff_allowed = 10
    start_delay_s = 40

    def __init__(
        self,
        inventory: str | None = None,
        limit: str | None = None,
        user: str | None = None,
        key_filepath: Path | None = None,
    ) -> None:
        limits_list: list[str] | None = None
        if isinstance(limit, str):
            limits_list = limit.split(",")
            limits_list = [_host for _host in limits_list if len(_host) >= 1]
        if isinstance(inventory, str) and Path(inventory).exists() and Path(inventory).is_file():
            inventory = Path(inventory)
        if isinstance(inventory, str):
            hostlist = inventory.split(",")
            hostlist = [_host for _host in hostlist if len(_host) >= 1]
            if limits_list is not None:
                hostlist = list(set(hostlist) & set(limits_list))
            hostnames = {hostname: hostname for hostname in hostlist}
        else:
            # look at all these directories for inventory-file
            if inventory in {"", None}:
                inventories = [
                    "/etc/shepherd/herd.yml",
                    "~/herd.yml",
                    "inventory/herd.yml",
                    "herd.yml",  # TODO: use XDG_CACHE_HOME
                ]
            else:
                inventories = [inventory]
            host_path = None
            for inventory in inventories:
                if Path(inventory).exists():
                    host_path = Path(inventory)

            if host_path is None:
                raise FileNotFoundError(", ".join(inventories))

            with host_path.open(encoding="utf-8-sig") as stream:
                try:
                    inventory_data = yaml.safe_load(stream)
                except yaml.YAMLError as _xpt:
                    raise FileNotFoundError(
                        "Couldn't read inventory file %s, please provide a valid one",
                        host_path.as_posix(),
                    ) from _xpt
            logger.info("Shepherd-Inventory = '%s'", host_path.as_posix())

            hostlist = []
            hostnames: dict[str, str] = {}
            for hostname, hostvars in inventory_data["sheep"]["hosts"].items():
                if isinstance(limits_list, list) and (hostname not in limits_list):
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
                "Provide remote hosts (either inventory empty or limit does not match)",
            )

        connect_kwargs: dict[str, str] = {}
        if key_filepath is not None:
            connect_kwargs["key_filename"] = str(key_filepath)

        self.group: Group = Group(
            *hostlist,
            user=user,
            connect_timeout=5,
            connect_kwargs=connect_kwargs,
        )
        self.hostnames: dict[str, str] = hostnames

        logger.info("Herd consists of %d sheep", len(self.group))

    def __del__(self) -> None:
        # ... overcautious closing of connections
        if not hasattr(self, "group") or not isinstance(self.group, Group):
            return
        with contextlib.suppress(TypeError):
            for cnx in self.group:
                cnx.close()
                del cnx

    def __enter__(self) -> Self:
        self._open()
        if len(self.group) < 1:
            logger.error("No remote sheep in current herd! Will run dry")
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        if not hasattr(self, "group") or not isinstance(self.group, Group):
            return
        with contextlib.suppress(TypeError):
            for cnx in self.group:
                cnx.close()

    def __getitem__(self, key: str) -> Any:
        if key in self.hostnames:
            return self.hostnames[key]
        raise KeyError

    def __repr__(self) -> dict:
        return self.hostnames

    @staticmethod
    def _thread_open(
        cnx: Connection,
    ) -> None:
        if cnx.is_connected:
            return
        try:
            cnx.open()
        except (NoValidConnectionsError, SSHException, TimeoutError):
            logger.error(
                "[%s] failed to open connection -> will exclude node from inventory",
                cnx.host,  # = IP
            )
            cnx.close()

    def _open(self) -> None:
        """Open Connection on all Nodes."""
        threads = {}
        for cnx in self.group:
            _name = self.hostnames[cnx.host]
            threads[_name] = threading.Thread(target=self._thread_open, args=[cnx])
            threads[_name].start()
        for host, thread in threads.items():
            thread.join(timeout=10.0)
            if thread.is_alive():
                logger.error(
                    "Connection.Open() did fail to finish on %s - will delete that thread",
                    host,
                )
            del thread  # ... overcautious
        self.group = [cnx for cnx in self.group if cnx.is_connected]

    @staticmethod
    def _thread_run(
        cnx: Connection,
        sudo: bool,  # noqa: FBT001
        cmd: str,
        results: dict[str, Result],
        hostname: str,
    ) -> None:
        if not cnx.is_connected:
            return
        try:
            if sudo:
                results[hostname] = cnx.sudo(cmd, warn=True, hide=True)
            else:
                results[hostname] = cnx.run(cmd, warn=True, hide=True)
        except (NoValidConnectionsError, SSHException, TimeoutError):
            logger.error(
                "[%s] failed to run '%s' -> will exclude node from inventory",
                cnx.host,  # IP
                cmd,
            )
            cnx.close()

    @validate_call
    def run_cmd(
        self,
        cmd: str,
        exclusive_host: str | None = None,
        *,
        sudo: bool = False,
        verbose: bool = True,
    ) -> dict[str, Result]:
        """Run COMMAND on the shell -> Returns output-results.

        NOTE: in case of error on a node that corresponding dict value is unavailable
        """
        results: dict[str, Result] = {}
        threads = {}
        level = logging.INFO if verbose else logging.DEBUG
        logger.log(level, "Sheep-CMD = %s", cmd)
        for cnx in self.group:
            _name = self.hostnames[cnx.host]
            if exclusive_host and _name != exclusive_host:
                continue
            threads[_name] = threading.Thread(
                target=self._thread_run,
                args=(cnx, sudo, cmd, results, _name),
            )
            threads[_name].start()
        for host, thread in tqdm(
            threads.items(), desc="  .. joining threads", unit="n", leave=False
        ):
            thread.join()  # timeout=10.0
            if thread.is_alive():
                logger.error(
                    "Command.Run() did fail to finish on %s - will delete that thread",
                    host,
                )
            del thread  # ... overcautious
        if len(results) < 1:
            logger.error("ZERO nodes answered - check your config")
        return results

    @staticmethod
    def print_output(
        replies: dict[str, Result],
        *,
        verbose: bool = False,
    ) -> None:
        """Log output-results of shell commands."""
        for hostname, reply in replies.items():
            # TODO: incorrect when sheep are missing in between
            #       -> also throw out in hostname-dict?
            if not verbose and reply.exited == 0:
                continue
            if len(reply.stdout) > 0:
                logger.info("\n************** %s - stdout **************", hostname)
                logger.info(reply.stdout)
            if len(reply.stderr) > 0:
                logger.error("\n~~~~~~~~~~~~~~ %s - stderr ~~~~~~~~~~~~~~", hostname)
                logger.error(reply.stderr)
            logger.info("Exit-code of %s = %s", hostname, reply.exited)

    @staticmethod
    def _thread_put(
        cnx: Connection,
        src: Path | StringIO,
        dst: PurePosixPath,
        force_overwrite: bool,  # noqa: FBT001
    ) -> None:
        if isinstance(src, StringIO):
            filename = dst.name
        else:
            filename = src.name
            src = str(src)

        if not dst.suffix and not str(dst).endswith("/"):
            dst = PurePosixPath(str(dst) + "/")

        if not cnx.is_connected:
            return

        tmp_path = PurePosixPath("/tmp") / filename  # noqa: S108
        logger.debug("temp-path for %s is %s", cnx.host, tmp_path)
        try:
            cnx.put(src, tmp_path.as_posix())
            xtr_arg = "-f" if force_overwrite else "-n"
            cnx.sudo(f"mv {xtr_arg} {tmp_path} {dst}", warn=True, hide=True)
        except (NoValidConnectionsError, SSHException, TimeoutError):
            logger.error(
                "[%s] failed to put to '%s' -> will exclude node from inventory",
                cnx.host,
                dst.as_posix(),
            )
            cnx.close()

    def put_file(
        self,
        src: StringIO | Path | str,
        dst: PurePosixPath | str,
        *,
        force_overwrite: bool = False,
    ) -> None:
        if isinstance(src, StringIO):
            src_path = src
        else:
            src_path = Path(src).absolute()
            if not src_path.exists():
                raise FileNotFoundError(
                    "Local source file '%s' does not exist!",
                    src_path,
                )
            logger.info("Local source path = %s", src_path)

        if dst is None:
            dst_path = self.path_default
            logger.debug("Remote path not provided -> use default = %s", dst_path)
        else:
            dst_path = PurePosixPath(dst)
            dst_posix = dst_path.as_posix()
            is_allowed = False
            for path_allowed in self._remote_paths_allowed:
                if dst_posix.startswith(path_allowed.as_posix()):
                    is_allowed = True
            if not is_allowed:
                raise NameError("provided path was forbidden ('%s')", dst_posix)

        threads = {}
        for cnx in self.group:
            _name = self.hostnames[cnx.host]
            threads[_name] = threading.Thread(
                target=self._thread_put,
                args=(cnx, src_path, dst_path, force_overwrite),
            )
            threads[_name].start()
        for host, thread in tqdm(
            threads.items(), desc="  .. joining threads", unit="n", leave=False
        ):
            thread.join()  # timeout=10.0
            if thread.is_alive():
                logger.error(
                    "File.Put() did fail to finish on %s - will delete that thread",
                    host,
                )
            del thread  # ... overcautious

    @staticmethod
    def _thread_get(cnx: Connection, src: PurePosixPath, dst: Path) -> None:
        if not cnx.is_connected:
            return
        try:
            cnx.get(src.as_posix(), local=dst.as_posix())
        except (NoValidConnectionsError, SSHException, TimeoutError):
            logger.error(
                "[%s] failed to get '%s' -> will exclude node from inventory",
                cnx.host,
                src.as_posix(),
            )
            cnx.close()

    @validate_call
    def get_file(
        self,
        src: PurePosixPath | str,
        dst_dir: Path | str,
        exclusive_host: str | None = None,
        *,
        timestamp: bool = False,
        separate: bool = False,
        delete_src: bool = False,
    ) -> bool:
        time_str = time.strftime("%Y_%m_%dT%H_%M_%S")
        xtra_ts = f"_{time_str}" if timestamp else ""
        failed_retrieval = False

        threads = {}
        dst_paths = {}

        # assemble file-names
        src_path: PurePosixPath = (
            PurePosixPath(src) if PurePosixPath(src).is_absolute() else self.path_default / src
        )

        for i, cnx in enumerate(self.group):
            hostname = self.hostnames[cnx.host]
            if separate:
                target_path = Path(dst_dir) / hostname
                xtra_node = ""
            else:
                target_path = Path(dst_dir)
                xtra_node = "" if hostname in src_path.stem else f"_{hostname}"

            dst_paths[i] = target_path / (src_path.stem + xtra_ts + xtra_node + src_path.suffix)

        # check if file is present
        replies = self.run_cmd(
            sudo=False, exclusive_host=exclusive_host, cmd=f"test -f {src_path}", verbose=False
        )

        # try to fetch data
        for i, cnx in enumerate(self.group):
            hostname = self.hostnames[cnx.host]
            if not isinstance(replies.get(hostname), Result):
                continue
            if abs(replies[hostname].exited) != 0:
                logger.error(
                    "remote file '%s' does not exist on node %s",
                    src_path,
                    hostname,
                )
                failed_retrieval = True
                continue

            if not dst_paths[i].parent.exists():
                logger.info("creating local dir of %s", dst_paths[i])
                dst_paths[i].parent.mkdir()

            logger.debug(
                "retrieving remote src-file '%s' from %s to local dst '%s'",
                src_path,
                hostname,
                dst_paths[i],
            )

            threads[i] = threading.Thread(
                target=self._thread_get,
                args=(cnx, src_path, dst_paths[i]),
            )
            threads[i].start()
        logger.debug("  .. threads started - will wait until finished")
        for i, cnx in enumerate(
            tqdm(self.group, desc="  .. joining threads", unit="n", leave=False)
        ):
            hostname = self.hostnames[cnx.host]
            if not isinstance(replies.get(hostname), Result):
                continue
            if replies[hostname].exited != 0:
                continue
            threads[i].join()  # timeout=10.0
            if threads[i].is_alive():
                logger.error(
                    "Command.Run() did fail to finish on %s - will delete that thread",
                    hostname,
                )
            del threads[i]  # ... overcautious
            if delete_src:
                logger.info(
                    "deleting %s from remote %s",
                    src_path,
                    hostname,
                )
                cnx.sudo(f"rm {src_path}", hide=True)

        del threads
        return failed_retrieval

    def find_consensus_time(self) -> tuple[datetime, float]:
        """Find a start time in the future when all nodes should start service.

        In order to run synchronously, all nodes should start at the same time.
        This is achieved by querying all nodes to check any large time offset,
        agreeing on a common time in the future and waiting for that time on each
        node.
        """
        # Get the current time on each target node
        replies = self.run_cmd(sudo=False, cmd="date --iso-8601=seconds", verbose=False)
        ts_nows = [datetime.fromisoformat(reply.stdout.rstrip()) for reply in replies.values()]
        if len(ts_nows) == 0:
            raise RuntimeError("No active hosts found to synchronize.")
        ts_max = max(ts_nows)
        ts_min = min(ts_nows)
        ts_diff = ts_max.timestamp() - ts_min.timestamp()
        # Check for excessive time difference among nodes
        if ts_diff > self.timestamp_diff_allowed:
            raise RuntimeError(
                "Time difference between hosts greater %f s",
                self.timestamp_diff_allowed,
            )
        if ts_max.tzinfo is None:
            logger.error("Provided time from host should have time-zone data!")
        # We need to estimate a future point in time such that all nodes are ready
        ts_start = ts_max + timedelta(seconds=self.start_delay_s)
        return ts_start, float(self.start_delay_s + ts_diff / 2)

    @validate_call
    def put_task(
        self,
        task: Path | ShpModel,
        remote_path: PurePosixPath | str = "/etc/shepherd/config.yaml",
    ) -> None:
        """Transfer shepherd tasks to the group of hosts / sheep.

        Rolls out a configuration file according to the given command and parameters
        service.

        """
        if isinstance(task, ShpModel):
            task_dict = task.model_dump(exclude_unset=True)
            task_wrap = Wrapper(
                datatype=type(task).__name__,
                created=datetime.now(tz=local_tz()),
                parameters=task_dict,
            )
            task_yaml = yaml.safe_dump(
                task_wrap.model_dump(exclude_unset=True),
                default_flow_style=False,
                sort_keys=False,
            )
            task = StringIO()  # TODO: wanted is StringIO(task_yaml), but large inputs produce bugs
            task.write(task_yaml)
        elif isinstance(task, Path):
            if not task.is_file() or not task.exists():
                raise FileNotFoundError("Task-Path must be an existing file")
            with task.open(encoding="utf-8-sig") as stream:
                task_yaml = yaml.safe_load(stream)
        else:
            raise TypeError("Task must either be model or path to a model")

        if self.check_status(warn=True):
            raise RuntimeError("Shepherd still active!")
        if not isinstance(remote_path, PurePath):
            remote_path = PurePosixPath(remote_path)

        logger.info(
            "Rolling out the config to '%s'",
            remote_path.as_posix(),
        )
        self.put_file(
            task,
            remote_path,
            force_overwrite=True,
        )

    @validate_call
    def check_status(self, *, warn: bool = False) -> bool:
        """Return true as long as one instance is still measuring.

        :param warn:
        :return: True is one node is still active
        """
        replies = self.run_cmd(sudo=True, cmd="systemctl status shepherd", verbose=False)
        active = False

        for cnx in self.group:
            hostname = self.hostnames[cnx.host]
            if not isinstance(replies.get(hostname), Result):
                continue
            if replies[hostname].exited != 3:
                active = True
                if warn:
                    logger.warning(
                        "shepherd still active on %s",
                        hostname,
                    )
                else:
                    logger.debug(
                        "shepherd still active on %s",
                        hostname,
                    )
                    # shepherd-herd -v shell-cmd -s "systemctl status shepherd"
        return active

    def get_last_usage(self) -> timedelta | None:
        """Gives time-delta of last testbed usage."""
        replies1 = self.run_cmd(sudo=True, cmd="tail -n 1 /var/shepherd/log.csv", verbose=False)
        replies2 = self.run_cmd(sudo=False, cmd="date --iso-8601=seconds", verbose=False)
        deltas = []
        for cnx in self.group:
            hostname = self.hostnames[cnx.host]
            if not isinstance(replies1.get(hostname), Result):
                continue
            if not isinstance(replies2.get(hostname), Result):
                continue
            if replies1[hostname].exited == 0:
                ts_end = datetime.fromisoformat(replies1[hostname].stdout.split(",")[1].strip())
                ts_now = datetime.fromisoformat(replies2[hostname].stdout.strip())
                deltas.append(ts_now - ts_end)
        if len(deltas) == 0:
            return None
        return min(deltas)

    def start_measurement(self) -> int:
        """Start shepherd service on the group of hosts."""
        if self.check_status(warn=True):
            logger.info("-> won't start while shepherd-instances are active")
            return 1

        replies = self.run_cmd(sudo=True, cmd="systemctl start shepherd")
        self.print_output(replies)
        return max([0] + [abs(reply.exited) for reply in replies.values()])

    def stop_measurement(self) -> int:
        logger.debug("Shepherd-nodes affected: %s", self.hostnames.values())
        replies = self.run_cmd(sudo=True, cmd="systemctl stop shepherd")
        exit_code = max([0] + [abs(reply.exited) for reply in replies.values()])
        logger.info("Shepherd was forcefully stopped")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)
        return exit_code

    @validate_call
    def poweroff(self, *, restart: bool) -> int:
        logger.debug("Shepherd-nodes affected: %s", self.hostnames.values())
        if restart:
            replies = self.run_cmd(sudo=True, cmd="reboot")
            logger.info("Command for rebooting nodes was issued")
        else:
            replies = self.run_cmd(sudo=True, cmd="poweroff")
            logger.info("Command for powering off nodes was issued")
        return max([0] + [abs(reply.exited) for reply in replies.values()])

    @validate_call
    def await_stop(self, timeout: int = 30) -> bool:
        ts_end = time.time() + timeout
        while self.check_status():
            if time.time() > ts_end:
                return self.check_status(warn=True)
            time.sleep(1)
        return False

    @validate_call
    def inventorize(self, output_path: Path) -> bool:
        """Collect information about the hosts, including the herd-server."""
        if output_path.is_file():
            raise ValueError(
                "Inventorize needs a dir, not a file '%s'",
                output_path.as_posix(),
            )
        file_path = PurePosixPath("/var/shepherd/inventory.yaml")
        self.run_cmd(
            sudo=True,
            cmd=f"shepherd-sheep inventorize --output-path {file_path.as_posix()}",
        )
        server_inv = Inventory.collect()
        output_path = Path(output_path)
        server_inv.to_file(
            path=Path(output_path) / "inventory_server.yaml",
            minimal=True,
        )
        return self.get_file(
            file_path,
            output_path,
            timestamp=False,
            separate=False,
            delete_src=True,
        )
        # TODO: best case - add all to one file or a new inventories-model?

    def resync(self) -> int:
        """Get current time via ntp and restart PTP on each sheep."""
        commands = [
            "systemctl stop phc2sys@eth0",
            "systemctl stop ptp4l@eth0",
            "ntpdate -s time.nist.gov",
            "systemctl start phc2sys@eth0",
            "systemctl start ptp4l@eth0",
            "shepherd-sheep fix",  # restarts kernel module
        ]
        exit_code = 0
        for command in commands:
            ret = self.run_cmd(sudo=True, cmd=command)
            self.print_output(ret, verbose=True)
            exit_code = max([exit_code] + [abs(reply.exited) for reply in ret.values()])

        # Get the current time on each target node
        replies_date = self.run_cmd(sudo=False, cmd="date --iso-8601=seconds", verbose=False)
        self.print_output(replies_date, verbose=True)
        # calc diff
        ts_nows = [datetime.fromisoformat(reply.stdout.rstrip()) for reply in replies_date.values()]
        if len(ts_nows) == 0:
            raise RuntimeError("No active hosts found to synchronize.")
        ts_max = max(ts_nows)
        ts_min = min(ts_nows)
        ts_diff = ts_max.timestamp() - ts_min.timestamp()
        if ts_diff > 5:
            logger.error("Timediff after resync is too large (%d s)", ts_diff)
            return 1
        logger.info("Timediff is OK (%d s)", ts_diff)
        return exit_code

    @validate_call
    def run_task(self, config: Path | ShpModel, *, attach: bool = False) -> int:
        if attach:
            remote_path = PurePosixPath("/etc/shepherd/config_for_herd.yaml")
            self.put_task(config, remote_path)
            command = f"shepherd-sheep --verbose run {remote_path.as_posix()}"
            replies = self.run_cmd(sudo=True, cmd=command)
            exit_code = max([0] + [abs(reply.exited) for reply in replies.values()])
            if exit_code:
                logger.error("Running Task failed - will exit now!")
            self.print_output(replies, verbose=True)

        else:
            remote_path = PurePosixPath("/etc/shepherd/config.yaml")
            self.put_task(config, remote_path)
            exit_code = self.start_measurement()
            logger.info("Shepherd started.")
            if exit_code > 0:
                logger.debug("-> max exit-code = %d", exit_code)
        return exit_code

    @validate_call
    def get_task_files(
        self,
        config: Path | ShpModel,
        dst_dir: Path | str,
        *,
        separate: bool = False,
        delete_src: bool = False,
    ) -> bool:
        tbed_id = tb_client.query_ids("Testbed")[0]
        tbed_di = tb_client.query_item("Testbed", tbed_id)
        tbed = Testbed(**tbed_di)
        if tbed.shared_storage:
            logger.info("Data should be locally at: %s", {tbed.data_on_server})

        wrap = prepare_task(config)
        tasks = extract_tasks(wrap, no_task_sets=False)
        failed = False
        for task in tasks:
            if hasattr(task, "output_path"):
                logger.info("General remote path is: %s", task.output_path)
                failed |= self.get_file(
                    task.output_path,
                    dst_dir,
                    separate=separate,
                    delete_src=delete_src,
                )
            elif hasattr(task, "get_output_paths"):
                for host, path in task.get_output_paths().items():
                    logger.info("Remote path of '%s' is: %s", host, path)
                    failed |= self.get_file(
                        path,
                        dst_dir,
                        exclusive_host=host,
                        separate=separate,
                        delete_src=delete_src,
                    )
        return failed

    def alive(self) -> bool:
        """Check if all remote hosts are present & responding.

        - Group is list of hosts with live connection,
        - hostnames contains all hosts in inventory
        """
        return len(self.group) >= len(self.hostnames)
