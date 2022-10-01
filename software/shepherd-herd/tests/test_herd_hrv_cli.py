import time

import pytest
from shepherd_herd import cli

from .conftest import wait_for_end


@pytest.mark.timeout(60)
def test_harv_example(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "-a",
            "cv20",
            "-d",
            "10",
            "-o",
            "pytest.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(60)
def test_harv_example_long(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "--algorithm",
            "cv20",
            "--duration",
            "10",
            "--output_path",
            "pytest.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(60)
def test_harv_example_fail(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "--algorithm",
            "ceeeveeeee",
            "--duration",
            "10",
            "--output_path",
            "pytest.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(60)
def test_harv_minimal(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        ["harvester"],
    )
    assert res.exit_code == 0
    time.sleep(10)
    # forced stop
    res = cli_runner.invoke(
        cli,
        ["-vvv", "stop"],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner)


@pytest.mark.timeout(60)
def test_harv_all_args(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "-a",
            "cv33",
            "-d",
            "10",
            "--force_overwrite",
            "--use_cal_default",
            "--start",
            "-o",
            "pytest.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(80)
def test_harv_no_start(cli_runner, stopped_herd) -> None:
    # Note: short timeout is the catch
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "-d",
            "10",
            "--no-start",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=10)
    # manual start
    res = cli_runner.invoke(
        cli,
        ["-vvv", "start"],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=60)


# TODO:
#   retrieve & check with datalib (length & validity)
