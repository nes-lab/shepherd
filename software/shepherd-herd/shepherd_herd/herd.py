"""
Herd-Baseclass
"""
import contextlib
import threading
import time
from datetime import datetime
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import yaml
from fabric import Connection
from fabric import Group
from fabric import Result
from paramiko.ssh_exception import NoValidConnectionsError
from paramiko.ssh_exception import SSHException
from pydantic import validate_call
from shepherd_core import Inventory
from shepherd_core import tb_client
from shepherd_core.data_models import ShpModel
from shepherd_core.data_models import Wrapper
from shepherd_core.data_models.task import extract_tasks
from shepherd_core.data_models.task import prepare_task
from shepherd_core.data_models.testbed import Testbed

from .logger import logger


class Herd:
    _remote_paths_allowed = [
        Path("/var/shepherd/recordings/"),  # default
        Path("/var/shepherd/"),
        Path("/etc/shepherd/"),
        Path("/tmp/"),  # noqa: S108
    ]
    path_default = _remote_paths_allowed[0]

    timestamp_diff_allowed = 10
    start_delay_s = 30

    def __init__(
        self,
        inventory: Optional[str] = None,
        limit: Optional[str] = None,
        user: Optional[str] = None,
        key_filepath: Optional[Path] = None,
    ):
        limits_list: Optional[List[str]] = None
        if isinstance(limit, str):
            limits_list = limit.split(",")
            limits_list = [_host for _host in limits_list if len(_host) >= 1]
        if (
            isinstance(inventory, str)
            and Path(inventory).exists()
            and Path(inventory).is_file()
        ):
            inventory = Path(inventory)
        if isinstance(inventory, str):
            hostlist = inventory.split(",")
            hostlist = [_host for _host in hostlist if len(_host) >= 1]
            if limits_list is not None:
                hostlist = list(set(hostlist) & set(limits_list))
            hostnames = {hostname: hostname for hostname in hostlist}
        else:
            # look at all these directories for inventory-file
            if inventory in ["", None]:
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
                    raise FileNotFoundError(
                        f"Couldn't read inventory file {host_path}, please provide a valid one",
                    )
            logger.info("Shepherd-Inventory = '%s'", host_path.as_posix())

            hostlist = []
            hostnames: Dict[str, str] = {}
            for hostname, hostvars in inventory_data["sheep"]["hosts"].items():
                if isinstance(limits_list, List) and (hostname not in limits_list):
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

        connect_kwargs: Dict[str, str] = {}
        if key_filepath is not None:
            connect_kwargs["key_filename"] = str(key_filepath)

        self.group: Group = Group(
            *hostlist,
            user=user,
            connect_timeout=5,
            connect_kwargs=connect_kwargs,
        )
        self.hostnames: Dict[str, str] = hostnames

        logger.info("Herd consists of %d sheep", len(self.group))

    def __del__(self):
        # ... overcautious closing of connections
        if not hasattr(self, "group") or not isinstance(self.group, Group):
            return
        with contextlib.suppress(TypeError):
            for cnx in self.group:
                cnx.close()
                del cnx

    def __enter__(self):
        self._open()
        if len(self.group) < 1:
            raise ValueError("No remote sheep in current herd!")
        return self

    def __exit__(self, *args):  # type: ignore
        if not hasattr(self, "group") or not isinstance(self.group, Group):
            return
        with contextlib.suppress(TypeError):
            for cnx in self.group:
                cnx.close()

    def __getitem__(self, key: str):
        if key in self.hostnames:
            return self.hostnames[key]
        raise KeyError

    def __repr__(self):
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
                cnx.host,
            )
            cnx.close()

    def _open(self) -> None:
        """Open Connection on all Nodes"""
        threads = {}
        for i, cnx in enumerate(self.group):
            threads[i] = threading.Thread(target=self._thread_open, args=[cnx])
            threads[i].start()
        for thread in threads.values():
            thread.join()
            del thread  # ... overcautious
        self.group = [cnx for cnx in self.group if cnx.is_connected]

    @staticmethod
    def _thread_run(
        cnx: Connection,
        sudo: bool,
        cmd: str,
        results: dict[int, Result],
        index: int,
    ) -> None:
        if not cnx.is_connected:
            return
        try:
            if sudo:
                results[index] = cnx.sudo(cmd, warn=True, hide=True)
            else:
                results[index] = cnx.run(cmd, warn=True, hide=True)
        except (NoValidConnectionsError, SSHException, TimeoutError):
            logger.error(
                "[%s] failed to run '%s' -> will exclude node from inventory",
                cnx.host,
                cmd,
            )
            cnx.close()

    @validate_call
    def run_cmd(self, cmd: str, sudo: bool = False) -> dict[int, Result]:
        """Run COMMAND on the shell -> Returns output-results
        NOTE: in case of error on a node that corresponding dict value is unavailable
        """
        results: dict[int, Result] = {}
        threads = {}
        logger.debug("Sheep-CMD = %s", cmd)
        for i, cnx in enumerate(self.group):
            threads[i] = threading.Thread(
                target=self._thread_run,
                args=(cnx, sudo, cmd, results, i),
            )
            threads[i].start()
        for thread in threads.values():
            thread.join()
            del thread  # ... overcautious
        if len(results) < 1:
            raise RuntimeError("ZERO nodes answered - check your config")
        return results

    def print_output(self, replies: dict[int, Result], verbose: bool = False) -> None:
        """Logs output-results of shell commands"""
        for i, hostname in enumerate(self.hostnames.values()):
            if not isinstance(replies.get(i), Result):
                continue
            if not verbose and replies[i].exited == 0:
                continue
            if len(replies[i].stdout) > 0:
                logger.info("\n************** %s - stdout **************", hostname)
                logger.info(replies[i].stdout)
            if len(replies[i].stderr) > 0:
                logger.error("\n~~~~~~~~~~~~~~ %s - stderr ~~~~~~~~~~~~~~", hostname)
                logger.error(replies[i].stderr)
            logger.info("Exit-code of %s = %s", hostname, replies[i].exited)

    @staticmethod
    def _thread_put(
        cnx: Connection,
        src: Union[Path, StringIO],
        dst: Path,
        force_overwrite: bool,
    ):
        if isinstance(src, StringIO):
            filename = dst.name
        else:
            filename = src.name
            src = str(src)

        if dst.suffix == "" and not str(dst).endswith("/"):
            dst = str(dst) + "/"

        if not cnx.is_connected:
            return

        tmp_path = Path("/tmp") / filename  # noqa: S108
        logger.debug("temp-path for %s is %s", cnx.host, tmp_path)
        try:
            cnx.put(src, str(tmp_path))  # noqa: S108
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
        src: Union[StringIO, Path, str],
        dst: Union[Path, str],
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
            logger.debug("Remote path not provided -> default = %s", dst_path)
        else:
            dst_path = Path(dst).absolute()
            is_allowed = False
            for path_allowed in self._remote_paths_allowed:
                if str(dst_path).startswith(str(path_allowed)):
                    is_allowed = True
            if not is_allowed:
                raise NameError(f"provided path was forbidden ('{dst_path}')")

        threads = {}
        for i, cnx in enumerate(self.group):
            threads[i] = threading.Thread(
                target=self._thread_put,
                args=(cnx, src_path, dst_path, force_overwrite),
            )
            threads[i].start()
        for thread in threads.values():
            thread.join()
            del thread  # ... overcautious

    @staticmethod
    def _thread_get(cnx: Connection, src: Path, dst: Path):
        if not cnx.is_connected:
            return
        try:
            cnx.get(str(src), local=str(dst))
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
        src: Union[Path, str],
        dst_dir: Union[Path, str],
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
        replies = self.run_cmd(sudo=False, cmd=f"test -f {src_path}")

        # try to fetch data
        for i, cnx in enumerate(self.group):
            if not isinstance(replies.get(i), Result):
                continue
            hostname = self.hostnames[cnx.host]
            if replies[i].exited > 0:
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

        for i, cnx in enumerate(self.group):
            hostname = self.hostnames[cnx.host]
            if replies[i].exited > 0:
                continue
            threads[i].join()
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

    def find_consensus_time(self) -> Tuple[datetime, float]:
        """Finds a start time in the future when all nodes should start service

        In order to run synchronously, all nodes should start at the same time.
        This is achieved by querying all nodes to check any large time offset,
        agreeing on a common time in the future and waiting for that time on each
        node.
        """
        # Get the current time on each target node
        replies = self.run_cmd(sudo=False, cmd="date --iso-8601=seconds")
        ts_nows = [
            datetime.fromisoformat(reply.stdout.rstrip()) for reply in replies.values()
        ]
        ts_max = max(ts_nows)
        ts_min = min(ts_nows)
        ts_diff = ts_max.timestamp() - ts_min.timestamp()
        # Check for excessive time difference among nodes
        if ts_diff > self.timestamp_diff_allowed:
            raise Exception(
                f"Time difference between hosts greater {self.timestamp_diff_allowed} s",
            )
        if ts_max.tzinfo is None:
            logger.error("Provided time from host should have time-zone data!")
        # We need to estimate a future point in time such that all nodes are ready
        ts_start = ts_max + timedelta(seconds=self.start_delay_s)
        return ts_start, float(self.start_delay_s + ts_diff / 2)

    @validate_call
    def put_task(
        self,
        task: Union[Path, ShpModel],
        remote_path: Union[Path, str] = "/etc/shepherd/config.yaml",
    ) -> None:
        """transfers shepherd tasks to the group of hosts / sheep.

        Rolls out a configuration file according to the given command and parameters
        service.

        """
        if isinstance(task, ShpModel):
            task_dict = task.model_dump(exclude_unset=True)
            task_wrap = Wrapper(
                datatype=type(task).__name__,
                created=datetime.now(),
                parameters=task_dict,
            )
            task_yaml = yaml.safe_dump(
                task_wrap.model_dump(exclude_unset=True),
                default_flow_style=False,
                sort_keys=False,
            )
            task = StringIO(task_yaml)
        elif isinstance(task, Path):
            if not task.is_file() or not task.exists():
                raise ValueError("Task-Path must be existing file")
            with open(task) as stream:
                task_yaml = yaml.safe_load(stream)
        else:
            raise ValueError("Task must either be model or path to a model")

        if self.check_status(warn=True):
            raise RuntimeError("shepherd still active!")
        if not isinstance(remote_path, Path):
            remote_path = Path(remote_path)

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
    def check_status(self, warn: bool = False) -> bool:
        """Returns true as long as one instance is still measuring

        :param warn:
        :return: True is one node is still active
        """
        replies = self.run_cmd(sudo=True, cmd="systemctl status shepherd")
        active = False

        for i, cnx in enumerate(self.group):
            if not isinstance(replies.get(i), Result):
                continue
            if replies[i].exited != 3:
                active = True
                if warn:
                    logger.warning(
                        "shepherd still active on %s",
                        self.hostnames[cnx.host],
                    )
                else:
                    logger.debug(
                        "shepherd still active on %s",
                        self.hostnames[cnx.host],
                    )
        return active

    def start_measurement(self) -> int:
        """Starts shepherd service on the group of hosts."""
        if self.check_status(warn=True):
            logger.info("-> won't start while shepherd-instances are active")
            return 1
        else:
            replies = self.run_cmd(sudo=True, cmd="systemctl start shepherd")
            self.print_output(replies)
            return max([reply.exited for reply in replies.values()])

    def stop_measurement(self) -> int:
        logger.debug("Shepherd-nodes affected: %s", self.hostnames.values())
        replies = self.run_cmd(sudo=True, cmd="systemctl stop shepherd")
        exit_code = max([reply.exited for reply in replies.values()])
        logger.info("Shepherd was forcefully stopped")
        if exit_code > 0:
            logger.debug("-> max exit-code = %d", exit_code)
        return exit_code

    @validate_call
    def poweroff(self, restart: bool) -> int:
        logger.debug("Shepherd-nodes affected: %s", self.hostnames.values())
        if restart:
            replies = self.run_cmd(sudo=True, cmd="reboot")
            logger.info("Command for rebooting nodes was issued")
        else:
            replies = self.run_cmd(sudo=True, cmd="poweroff")
            logger.info("Command for powering off nodes was issued")
        exit_code = max([reply.exited for reply in replies.values()])
        return exit_code

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
        """Collects information about the hosts, including the herd-server,
        return True on failure
        """
        if output_path.is_file():
            raise ValueError(
                f"Inventorize needs a dir, not a file '{output_path.as_posix()}'",
            )
        file_path = Path("/var/shepherd/inventory.yaml")
        self.run_cmd(
            sudo=True,
            cmd=f"shepherd-sheep inventorize --output_path {file_path.as_posix()}",
        )
        server_inv = Inventory.collect()
        output_path = Path(output_path)
        server_inv.to_file(
            path=Path(output_path) / "inventory_server.yaml",
            minimal=True,
        )
        failed = self.get_file(
            file_path,
            output_path,
            timestamp=False,
            separate=False,
            delete_src=True,
        )
        # TODO: best case - add all to one file or a new inventories-model?
        return failed

    @validate_call
    def run_task(self, config: Union[Path, ShpModel], attach: bool = False) -> int:
        if attach:
            remote_path = Path("/etc/shepherd/config_for_herd.yaml")
            self.put_task(config, remote_path)
            command = f"shepherd-sheep --verbose run {remote_path.as_posix()}"
            replies = self.run_cmd(sudo=True, cmd=command)
            exit_code = max([reply.exited for reply in replies.values()])
            if exit_code:
                logger.error("Running Task failed - will exit now!")
            self.print_output(replies, True)

        else:
            remote_path = Path("/etc/shepherd/config.yaml")
            self.put_task(config, remote_path)
            exit_code = self.start_measurement()
            logger.info("Shepherd started.")
            if exit_code > 0:
                logger.debug("-> max exit-code = %d", exit_code)
        return exit_code

    @validate_call
    def get_task_files(
        self,
        config: Union[Path, ShpModel],
        dst_dir: Union[Path, str],
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
                failed |= self.get_file(task.output_path, dst_dir, separate, delete_src)
            if hasattr(task, "get_output_paths"):
                for host, path in task.get_output_paths().items():
                    logger.info("Remote path of '%s' is: %s, WON'T COPY", host, path)
                    raise RuntimeError("FN not finished, not needed ATM")  # TODO
        return failed
        pass
