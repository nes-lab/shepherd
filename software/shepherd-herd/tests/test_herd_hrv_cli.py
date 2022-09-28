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
        [
            "harvester",
            "-d",
            "10",  # not needed, but better stop automatically
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


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


@pytest.mark.timeout(10)
def test_harv_no_start(cli_runner, stopped_herd) -> None:
    # Note: short timeout is the catch
    # -> also minimal arg-set without -d (not tested prior)
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "--no-start",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner)

# TODO:
#   forcefully stop
#   retrieve & check
