import time

import pytest
from shepherd_herd.cli import cli

from .conftest import generate_h5_file
from .conftest import wait_for_end


@pytest.mark.timeout(60)
def test_emu_prepare(cli_runner, stopped_herd, tmp_path) -> None:
    # distribute file and emulate from it in following tests
    test_file = generate_h5_file(tmp_path, "pytest_src.h5")
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "distribute",
            str(test_file),
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner)


@pytest.mark.timeout(120)
def test_emu_example(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "--virtsource",
            "BQ25504",
            "-o",
            "pytest_emu.h5",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=20)


@pytest.mark.timeout(60)
def test_emu_example_fail(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "--virtsource",
            "BQ25504",
            "-o",
            "pytest_emu.h5",
            "pytest_NonExisting.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=15)


@pytest.mark.timeout(120)
def test_emu_minimal(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "emulator",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=20)


@pytest.mark.timeout(120)
def test_emu_all_args_long(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "--duration",
            "10",
            "--force_overwrite",
            "--use_cal_default",
            "--enable_io",
            "--io_target",
            "A",
            "--pwr_target",
            "A",
            "--aux_voltage",
            "1.6",
            "--virtsource",
            "BQ25504",
            "--output_path",
            "pytest_emu.h5",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(120)
def test_emu_all_args_short(cli_runner, stopped_herd) -> None:
    # short arg or opposite bool val
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "10",
            "-f",
            "-c",
            "--disable_io",
            "--io_target",
            "B",
            "--pwr_target",
            "B",
            "-x",
            "1.4",
            "-a",
            "BQ25570",
            "-o",
            "pytest_emu.h5",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(150)
def test_emu_no_start(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "20",
            "-o",
            "pytest_emu.h5",
            "--no-start",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=15)
    # manual start
    res = cli_runner.invoke(
        cli,
        ["-vvv", "start"],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(60)
def test_emu_force_stop(cli_runner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "emulator",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    time.sleep(10)
    # forced stop
    res = cli_runner.invoke(
        cli,
        ["-vvv", "stop"],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=10)


# TODO: retrieve & check with datalib
