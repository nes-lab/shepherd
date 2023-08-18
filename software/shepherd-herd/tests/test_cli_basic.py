import os
from pathlib import Path

import pytest
from shepherd_herd.cli import cli

from .conftest import extract_first_sheep
from .conftest import generate_h5_file


@pytest.mark.timeout(10)
def test_run_standard(cli_runner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_run_extra(cli_runner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "shell-cmd",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_run_fail(cli_runner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "shell-command",
            "date",
        ],
    )
    assert res.exit_code != 0


@pytest.mark.timeout(10)
def test_run_sudo(cli_runner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "shell-cmd",
            "-s",
            "echo 'it's me: $USER",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_run_sudo_long(cli_runner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "shell-cmd",
            "--sudo",
            "echo 'it's me: $USER",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_inventory(cli_runner, local_herd: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-i",
            local_herd.as_posix(),
            "-vvv",
            "shell-cmd",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_inventory_long(cli_runner, local_herd: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "--inventory",
            local_herd.as_posix(),
            "--verbose",
            "=3",
            "shell-cmd",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit(cli_runner, local_herd: Path) -> None:
    sheep = extract_first_sheep(local_herd)
    res = cli_runner.invoke(
        cli,
        [
            "-i",
            local_herd.as_posix(),
            "-l",
            f"{sheep},",
            "-vvv",
            "shell-cmd",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit_long(cli_runner, local_herd: Path) -> None:
    sheep = extract_first_sheep(local_herd)
    res = cli_runner.invoke(
        cli,
        [
            "-i",
            local_herd.as_posix(),
            "--limit",
            f"{sheep},",
            "-vvv",
            "shell-cmd",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit_fail(cli_runner, local_herd: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-i",
            local_herd.as_posix(),
            "-l",
            "MrMeeseeks,",
            "-vvv",
            "shell-cmd",
            "date",
        ],
    )
    assert res.exit_code != 0


def test_distribute_retrieve_std(cli_runner, tmp_path: Path) -> None:
    test_file = generate_h5_file(tmp_path, "pytest_deploy.h5")
    elem_count1 = len(os.listdir(tmp_path))
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "distribute",
            test_file.as_posix(),
        ],
    )
    assert res.exit_code == 0
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "retrieve",
            "-f",
            "-t",
            "-d",
            test_file.name,
            tmp_path.as_posix(),
        ],
    )
    assert res.exit_code == 0
    elem_count2 = len(os.listdir(tmp_path))
    # file got deleted in prev retrieve, so fail now
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "retrieve",
            "-s",
            test_file.name,
            tmp_path.as_posix(),
        ],
    )
    assert res.exit_code != 0
    elem_count3 = len(os.listdir(tmp_path))
    assert elem_count1 < elem_count2
    assert elem_count2 == elem_count3


def test_distribute_retrieve_etc(cli_runner, tmp_path: Path) -> None:
    test_file = generate_h5_file(tmp_path, "pytest_deploy.h5")
    elem_count1 = len(os.listdir(tmp_path))
    dir_remote = "/etc/shepherd/"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "distribute",
            "--remote-path",
            dir_remote,
            test_file.as_posix(),
        ],
    )
    assert res.exit_code == 0
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "retrieve",
            "--force-stop",
            "--separate",
            "--delete",
            dir_remote + test_file.name,
            tmp_path.as_posix(),
        ],
    )
    assert res.exit_code == 0
    elem_count2 = len(os.listdir(tmp_path))
    # file got deleted in prev retrieve, so fail now
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "retrieve",
            "--timestamp",
            dir_remote + test_file.name,
            tmp_path.as_posix(),
        ],
    )
    assert res.exit_code != 0
    elem_count3 = len(os.listdir(tmp_path))
    assert elem_count1 < elem_count2
    assert elem_count2 == elem_count3


def test_distribute_retrieve_var(cli_runner, tmp_path: Path) -> None:
    test_file = generate_h5_file(tmp_path, "pytest_deploy.h5")
    elem_count1 = len(os.listdir(tmp_path))
    dir_remote = "/var/shepherd/"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "distribute",
            "-r",
            dir_remote,
            test_file.as_posix(),
        ],
    )
    assert res.exit_code == 0
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "retrieve",
            "--force-stop",
            "--separate",
            "--delete",
            dir_remote + test_file.name,
            tmp_path.as_posix(),
        ],
    )
    assert res.exit_code == 0
    elem_count2 = len(os.listdir(tmp_path))
    # file got deleted in prev retrieve, so fail now
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "retrieve",
            "--timestamp",
            dir_remote + test_file.name,
            tmp_path.as_posix(),
        ],
    )
    assert res.exit_code != 0
    elem_count3 = len(os.listdir(tmp_path))
    assert elem_count1 < elem_count2
    assert elem_count2 == elem_count3


# TODO: test providing user and key filename
# TODO: test poweroff (reboot)
# TODO: test sudo
