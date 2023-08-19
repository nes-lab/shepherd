from pathlib import Path

import pytest
from shepherd_herd.cli import cli

# NOTE: (almost) direct copy between shepherd-herd & python-package
# differences: import _herd, .mark.hardware, shepherd_up / stopped_herd


@pytest.fixture
def fw_example() -> Path:
    here = Path(__file__).absolute()
    name = "firmware_nrf52_powered.hex"
    return here.parent / name


@pytest.fixture
def fw_empty(tmp_path: Path) -> Path:
    store_path = tmp_path / "firmware_null.hex"
    with open(store_path, "w") as f:
        f.write("")
    return store_path


@pytest.mark.timeout(60)
def test_cli_program_minimal(cli_runner, fw_example: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "program",
            "--simulate",
            fw_example.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(60)
def test_cli_program_swd_explicit(cli_runner, fw_example: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
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
            fw_example.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(60)
def test_cli_program_swd_explicit_short(
    cli_runner,
    fw_example: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
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
            fw_example.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(60)
def test_cli_program_sbw_explicit(cli_runner, fw_example: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
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
            fw_example.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.timeout(60)
def test_cli_program_file_defective_a(cli_runner, fw_empty: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "program",
            "--simulate",
            fw_empty.as_posix(),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.timeout(60)
def test_cli_program_file_defective_b(cli_runner, tmp_path: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "program",
            "--simulate",
            tmp_path.as_posix(),  # Directory
        ],
    )
    assert res.exit_code != 0


@pytest.mark.timeout(60)
def test_cli_program_file_defective_c(cli_runner, tmp_path: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "program",
            "--simulate",
            str(tmp_path / "file_abc.bin"),  # non_existing file
        ],
    )
    assert res.exit_code != 0


@pytest.mark.timeout(60)
def test_cli_program_datarate_invalid_a(
    cli_runner,
    fw_example: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "program",
            "--datarate",
            "2000000",  # too fast
            "--simulate",
            fw_example.as_posix(),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.timeout(60)
def test_cli_program_datarate_invalid_b(
    cli_runner,
    fw_example: Path,
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "program",
            "--datarate",
            "0",  # impossible
            "--simulate",
            fw_example.as_posix(),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.timeout(60)
def test_cli_program_target_invalid(cli_runner, fw_example: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "program",
            "--mcu-type",
            "arduino",
            "--simulate",
            fw_example.as_posix(),
        ],
    )
    assert res.exit_code != 0


# not testable ATM (through CLI)
#   - fail pins 3x (pin_num is identical)
#   - fail wrong target (internally, fail in kModule)
#   - datasize > mem_size
