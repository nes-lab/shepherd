import os

import pytest
from shepherd_herd.cli import cli

from .conftest import extract_first_sheep
from .conftest import generate_h5_file


@pytest.mark.timeout(10)
def test_run_standard(cli_runner) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "run",
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
            "run",
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
            "runnnn",
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
            "run",
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
            "run",
            "--sudo",
            "echo 'it's me: $USER",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_inventory(cli_runner, local_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-i",
            str(local_herd),
            "-vvv",
            "run",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_inventory_long(cli_runner, local_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "--inventory",
            str(local_herd),
            "--verbose",
            "=3",
            "run",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit(cli_runner, local_herd) -> None:
    sheep = extract_first_sheep(local_herd)
    res = cli_runner.invoke(
        cli,
        [
            "-i",
            str(local_herd),
            "-l",
            f"{sheep},",
            "-vvv",
            "run",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit_long(cli_runner, local_herd) -> None:
    sheep = extract_first_sheep(local_herd)
    res = cli_runner.invoke(
        cli,
        [
            "-i",
            str(local_herd),
            "--limit",
            f"{sheep},",
            "-vvv",
            "run",
            "date",
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(10)
def test_provide_limit_fail(cli_runner, local_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-i",
            str(local_herd),
            "-l",
            "MrMeeseeks,",
            "-vvv",
            "run",
            "date",
        ],
    )
    assert res.exit_code != 0


def test_distribute_retrieve_std(cli_runner, tmp_path) -> None:
    test_file = generate_h5_file(tmp_path, "pytest_deploy.h5")
    elem_count1 = len(os.listdir(tmp_path))
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "distribute",
            str(test_file),
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
            str(test_file.name),
            str(tmp_path),
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
            str(test_file.name),
            str(tmp_path),
        ],
    )
    assert res.exit_code != 0
    elem_count3 = len(os.listdir(tmp_path))
    assert elem_count1 < elem_count2
    assert elem_count2 == elem_count3


def test_distribute_retrieve_etc(cli_runner, tmp_path) -> None:
    test_file = generate_h5_file(tmp_path, "pytest_deploy.h5")
    elem_count1 = len(os.listdir(tmp_path))
    dir_remote = "/etc/shepherd/"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "distribute",
            "--remote_path",
            dir_remote,
            str(test_file),
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
            dir_remote + str(test_file.name),
            str(tmp_path),
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
            dir_remote + str(test_file.name),
            str(tmp_path),
        ],
    )
    assert res.exit_code != 0
    elem_count3 = len(os.listdir(tmp_path))
    assert elem_count1 < elem_count2
    assert elem_count2 == elem_count3


def test_distribute_retrieve_var(cli_runner, tmp_path) -> None:
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
            str(test_file),
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
            dir_remote + str(test_file.name),
            str(tmp_path),
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
            dir_remote + str(test_file.name),
            str(tmp_path),
        ],
    )
    assert res.exit_code != 0
    elem_count3 = len(os.listdir(tmp_path))
    assert elem_count1 < elem_count2
    assert elem_count2 == elem_count3


# TODO: test providing user and key filename
# TODO: test poweroff (reboot)
# TODO: test sudo
