import time

import pytest
from click.testing import CliRunner
from shepherd_herd.herd_cli import cli

from .conftest import generate_h5_file
from .conftest import wait_for_end


@pytest.mark.timeout(60)
def test_emu_prepare(cli_runner: CliRunner, stopped_herd, tmp_path) -> None:
    # distribute file and emulate from it in following tests
    test_file = generate_h5_file(tmp_path, "pytest_src.h5")
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "distribute",
            "--force-overwrite",
            test_file.as_posix(),
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner)


@pytest.mark.timeout(150)
def test_emu_example(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "emulate",
            "--virtual-source",
            "BQ25504",
            "-o",
            "pytest_emu.h5",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=20)


@pytest.mark.timeout(60)
def test_emu_example_fail(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "emulate",
            "--virtual-source",
            "BQ25504",
            "-o",
            "pytest_emu.h5",
            "pytest_NonExisting.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=40)  # TODO: was 15 but got worse with core-lib


@pytest.mark.timeout(150)
def test_emu_minimal(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "emulate",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=20)


@pytest.mark.timeout(150)
def test_emu_all_args_long(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "emulate",
            "--duration",
            "10",
            "--force-overwrite",
            "--use-cal-default",
            "--enable-io",
            "--io-port",
            "A",
            "--pwr-port",
            "A",
            "--voltage-aux",
            "1.6",
            "--virtual-source",
            "BQ25504",
            "--output-path",
            "pytest_emu.h5",
            "pytest_src.h5",
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(150)
def test_emu_all_args_short(cli_runner: CliRunner, stopped_herd) -> None:
    # short arg or opposite bool val
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "emulate",
            "-d",
            "10",
            "-f",
            "-c",
            "--disable-io",
            "--io-port",
            "B",
            "--pwr-port",
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
def test_emu_no_start(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "emulate",
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
        ["-v", "start"],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=15)


@pytest.mark.timeout(60)
def test_emu_force_stop(cli_runner: CliRunner, stopped_herd) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "emulate",
            "pytest_src.h5",
        ],
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


# TODO: retrieve & verify with datalib
