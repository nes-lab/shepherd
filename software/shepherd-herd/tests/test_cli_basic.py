import os
from pathlib import Path

import pytest
from shepherd_herd.herd_cli import cli
from typer.testing import CliRunner

from .conftest import extract_first_sheep
from .conftest import generate_h5_file


@pytest.mark.timeout(10)
def test_run_standard(cli_runner: CliRunner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_run_extra(cli_runner: CliRunner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "-v",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_run_fail(cli_runner: CliRunner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-command",
            "-v",
            "date",
        ],
    )
    assert res.exit_code != 0


@pytest.mark.timeout(10)
def test_run_sudo(cli_runner: CliRunner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "-v",
            "-s",
            "echo 'it's me: $USER",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_run_sudo_long(cli_runner: CliRunner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "-v",
            "--sudo",
            "echo 'it's me: $USER",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_inventory(cli_runner: CliRunner, local_herd: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "-v",
            "-i",
            local_herd.as_posix(),
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_inventory_long(cli_runner: CliRunner, local_herd: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "--inventory",
            local_herd.as_posix(),
            "--verbose",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit(cli_runner: CliRunner, local_herd: Path) -> None:
    sheep = extract_first_sheep(local_herd)
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "-i",
            local_herd.as_posix(),
            "-l",
            f"{sheep},",
            "-v",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit_long(cli_runner: CliRunner, local_herd: Path) -> None:
    sheep = extract_first_sheep(local_herd)
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "-i",
            local_herd.as_posix(),
            "--limit",
            f"{sheep},",
            "-v",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit_fail(cli_runner: CliRunner, local_herd: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "shell-cmd",
            "-v",
            "-i",
            local_herd.as_posix(),
            "-l",
            "MrMeeseeks,",
            "date",
        ],
    )
    assert res.exit_code != 0


def test_distribute_retrieve_std(cli_runner: CliRunner, tmp_path: Path) -> None:
    test_file = generate_h5_file(tmp_path, "pytest_deploy.h5")
    elem_count1 = len(os.listdir(tmp_path))
    res = cli_runner.invoke(
        cli,
        [
            "distribute",
            "-v",
            test_file.as_posix(),
        ],
    )
    assert res.exit_code == 0
    res = cli_runner.invoke(
        cli,
        [
            "retrieve",
            "-v",
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
            "retrieve",
            "-v",
            "-s",
            test_file.name,
            tmp_path.as_posix(),
        ],
    )
    assert res.exit_code != 0
    elem_count3 = len(os.listdir(tmp_path))
    assert elem_count1 < elem_count2
    assert elem_count2 == elem_count3


def test_distribute_retrieve_etc(cli_runner: CliRunner, tmp_path: Path) -> None:
    test_file = generate_h5_file(tmp_path, "pytest_deploy.h5")
    elem_count1 = len(os.listdir(tmp_path))
    dir_remote = "/etc/shepherd/"
    res = cli_runner.invoke(
        cli,
        [
            "distribute",
            "-v",
            "--remote-path",
            dir_remote,
            test_file.as_posix(),
        ],
    )
    assert res.exit_code == 0
    res = cli_runner.invoke(
        cli,
        [
            "retrieve",
            "-v",
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
            "retrieve",
            "-v",
            "--timestamp",
            dir_remote + test_file.name,
            tmp_path.as_posix(),
        ],
    )
    assert res.exit_code != 0
    elem_count3 = len(os.listdir(tmp_path))
    assert elem_count1 < elem_count2
    assert elem_count2 == elem_count3


def test_distribute_retrieve_var(cli_runner: CliRunner, tmp_path: Path) -> None:
    test_file = generate_h5_file(tmp_path, "pytest_deploy.h5")
    elem_count1 = len(os.listdir(tmp_path))
    dir_remote = "/var/shepherd/"
    res = cli_runner.invoke(
        cli,
        [
            "distribute",
            "-v",
            "-r",
            dir_remote,
            test_file.as_posix(),
        ],
    )
    assert res.exit_code == 0
    res = cli_runner.invoke(
        cli,
        [
            "retrieve",
            "-v",
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
            "retrieve",
            "-v",
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
