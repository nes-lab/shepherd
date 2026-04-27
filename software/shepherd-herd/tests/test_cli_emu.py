import tempfile
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from click.testing import CliRunner
from shepherd_core import Reader
from shepherd_herd.herd_cli import cli

from .conftest import generate_h5_file
from .conftest import wait_for_end


@pytest.fixture(scope="module")
def eenv_file(cli_runner: CliRunner) -> Generator[Path, None, None]:
    # distribute file and emulate from it in following tests
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        file_path = generate_h5_file(tmp_path, "pytest_src.h5")
        res = cli_runner.invoke(
            cli, ["-v", "distribute", "--force-overwrite", file_path.as_posix()]
        )
        # -> expected at /tmp/pytest_src.h5
        assert res.exit_code == 0
        wait_for_end(cli_runner, timeout=60)
        yield file_path


@pytest.mark.timeout(150)
@pytest.mark.usefixtures("_herd_stopped")
def test_emu_example(cli_runner: CliRunner, eenv_file: Path) -> None:
    runtime = Reader(file_path=eenv_file, verbose=False).runtime_s
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "emulate",
            "--virtual-source",
            "BQ25504",
            "-o",
            "pytest_emu.h5",
            eenv_file.name,
        ],
    )  # -> config expected in /etc/shepherd/config.pickle
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=runtime)


@pytest.mark.timeout(80)
@pytest.mark.usefixtures("_herd_stopped")
def test_emu_example_fail(cli_runner: CliRunner) -> None:
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
    wait_for_end(cli_runner, timeout=60)  # TODO: was 15 but got worse with core-lib


@pytest.mark.timeout(150)
@pytest.mark.usefixtures("_herd_stopped")
def test_emu_minimal(cli_runner: CliRunner, eenv_file: Path) -> None:
    runtime = Reader(file_path=eenv_file, verbose=False).runtime_s
    res = cli_runner.invoke(cli, ["emulate", eenv_file.name])
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=runtime)


@pytest.mark.timeout(150)
@pytest.mark.usefixtures("_herd_stopped")
def test_emu_all_args_long(cli_runner: CliRunner, eenv_file: Path) -> None:
    runtime = Reader(file_path=eenv_file, verbose=False).runtime_s
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
            eenv_file.name,
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=runtime)


@pytest.mark.timeout(150)
@pytest.mark.usefixtures("_herd_stopped")
def test_emu_all_args_short(cli_runner: CliRunner, eenv_file: Path) -> None:
    runtime = Reader(file_path=eenv_file, verbose=False).runtime_s
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
            eenv_file.name,
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=runtime)


@pytest.mark.timeout(150)
@pytest.mark.usefixtures("_herd_stopped")
def test_emu_no_start(cli_runner: CliRunner, eenv_file: Path) -> None:
    runtime = Reader(file_path=eenv_file, verbose=False).runtime_s
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
            eenv_file.name,
        ],
    )
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=15)
    # manual start
    res = cli_runner.invoke(cli, ["-v", "start"])
    assert res.exit_code == 0
    wait_for_end(cli_runner, tmin=runtime)


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_herd_stopped")
def test_emu_force_stop(cli_runner: CliRunner, eenv_file: Path) -> None:
    res = cli_runner.invoke(cli, ["emulate", eenv_file.name])
    assert res.exit_code == 0
    time.sleep(10)
    # forced stop
    res = cli_runner.invoke(cli, ["-v", "stop"])
    assert res.exit_code == 0
    wait_for_end(cli_runner, timeout=10)


# TODO: retrieve & verify with shepherd-core
