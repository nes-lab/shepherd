from pathlib import Path

import pytest
from click.testing import CliRunner
from shepherd_sheep.cli import cli

# NOTE: (almost) direct copy between shepherd-herd & python-package
# differences: import _herd, .mark.hardware, shepherd_up / stopped_herd


@pytest.fixture
def fw_nrf() -> Path:
    here = Path(__file__).resolve()
    name = "firmware_nrf52_testable.hex"
    return here.parent / name


@pytest.fixture
def fw_msp() -> Path:
    here = Path(__file__).resolve()
    name = "firmware_msp430_testable.hex"
    return here.parent / name


@pytest.fixture
def fw_empty(tmp_path: Path) -> Path:
    store_path = tmp_path / "firmware_null.hex"
    with store_path.resolve().open("w", encoding="utf-8-sig") as fh:
        fh.write("")
    return store_path


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_minimal(
    cli_runner: CliRunner,
    fw_nrf: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "program",
            "--simulate",
            fw_nrf.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_swd_explicit(
    cli_runner: CliRunner,
    fw_nrf: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "--verbose",
            "program",
            "--target-port",
            "A",
            "--voltage",
            "2.0",
            "--datarate",
            "600000",
            "--mcu-type",
            "nrf52",
            "--mcu-port",
            "1",
            "--simulate",
            fw_nrf.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_swd_explicit_short(
    cli_runner: CliRunner,
    fw_nrf: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "program",
            "-p",
            "A",
            "-v",
            "2.0",
            "-d",
            "600000",
            "-t",
            "nrf52",
            "-m",
            "1",
            "--simulate",
            fw_nrf.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_sbw_explicit(
    cli_runner: CliRunner,
    fw_msp: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "--verbose",
            "program",
            "--target-port",
            "B",
            "--voltage",
            "1.5",
            "--datarate",
            "300000",
            "--mcu-type",
            "msp430",
            "--mcu-port",
            "2",
            "--simulate",
            fw_msp.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_file_defective_a(
    cli_runner: CliRunner,
    fw_empty: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "program",
            "--simulate",
            fw_empty.as_posix(),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_file_defective_b(
    cli_runner: CliRunner,
    tmp_path: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "program",
            "--simulate",
            tmp_path.as_posix(),  # Directory
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_file_defective_c(
    cli_runner: CliRunner,
    tmp_path: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "program",
            "--simulate",
            str(tmp_path / "file_abc.bin"),  # non_existing file
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_datarate_invalid_a(
    cli_runner: CliRunner,
    fw_nrf: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "program",
            "--datarate",
            "2000000",  # too fast
            "--simulate",
            fw_nrf.as_posix(),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_datarate_invalid_b(
    cli_runner: CliRunner,
    fw_nrf: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "program",
            "--datarate",
            "0",  # impossible
            "--simulate",
            fw_nrf.as_posix(),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("_shepherd_up")
def test_cli_program_target_invalid(
    cli_runner: CliRunner,
    fw_nrf: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-v",
            "program",
            "--mcu-type",
            "arduino",
            "--simulate",
            fw_nrf.as_posix(),
        ],
    )
    assert res.exit_code != 0


# not testable ATM (through CLI)
#   - fail pins 3x (pin_num is identical)
#   - fail wrong target (internally, fail in kModule)
#   - datasize > mem_size
