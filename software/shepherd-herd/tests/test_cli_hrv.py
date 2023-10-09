import time

import pytest
from click.testing import CliRunner
from shepherd_herd.herd_cli import cli

from .conftest import wait_for_end


@pytest.mark.timeout(150)
def test_hrv_example(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "harvest",
            "-a",
            "cv20",
            "-d",
            "10",
            "-o",
            "pytest_hrv.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(60)
def test_hrv_example_fail(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "harvest",
            "--virtual-harvester",
            "ceeeveeeee",
            "--duration",
            "10",
            "--output-path",
            "pytest_hrv.h5",
        ],
    )
    assert res.exit_code != 0
    wait_for_end(cli_runner, timeout=15)


@pytest.mark.timeout(60)
def test_hrv_minimal(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        ["harvest"],
    )
    assert res.exit_code == 0
    time.sleep(10)
    # forced stop
    res = cli_runner.invoke(
        cli,
        ["-v", "stop"],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=10)


@pytest.mark.timeout(150)
def test_hrv_all_args_long(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "harvest",
            "--virtual-harvester",
            "cv33",
            "--duration",
            "10",
            "--force-overwrite",
            "--use-cal-default",
            "--output-path",
            "pytest_hrv.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(150)
def test_hrv_all_args_short(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "harvest",
            "-a",
            "cv33",
            "-d",
            "10",
            "-f",
            "-c",
            "-o",
            "pytest_hrv.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(150)
def test_hrv_no_start(cli_runner: CliRunner, stopped_herd) -> None:
    # Note: short timeout is the catch
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "harvest",
            "-d",
            "10",
            "--no-start",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=15)
    # manual start
    res = cli_runner.invoke(
        cli,
        ["-v", "start"],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


# TODO: retrieve & verify with datalib (length & validity)
