from pathlib import Path

import pytest

from shepherd.cli import cli

# NOTE: (almost) direct copy between shepherd-herd & python-package
# differences: import _herd, .mark.hardware, shepherd_up / stopped_herd


@pytest.fixture
def fw_example() -> Path:
    here = Path(__file__).absolute()
    name = "firmware_nrf52_powered.hex"
    return here.parent / name


@pytest.fixture
def fw_empty(tmp_path) -> Path:
    store_path = tmp_path / "firmware_null.hex"
    with open(store_path, "w") as f:
        f.write("")
    return store_path


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_minimal(shepherd_up, cli_runner, fw_example: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--simulate",
            str(fw_example),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_swd_explicit(shepherd_up, cli_runner, fw_example: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--sel_a",
            "--voltage",
            "2.0",
            "--datarate",
            "600000",
            "--target",
            "nrf52",
            "--prog1",
            "--simulate",
            str(fw_example),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_swd_explicit_short(
    shepherd_up, cli_runner, fw_example: Path
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--sel_a",
            "-v",
            "2.0",
            "-d",
            "600000",
            "-t",
            "nrf52",
            "--prog1",
            "--simulate",
            str(fw_example),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_sbw_explicit(shepherd_up, cli_runner, fw_example: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--sel_b",
            "--voltage",
            "1.5",
            "--datarate",
            "300000",
            "--target",
            "msp430",
            "--prog2",
            "--simulate",
            str(fw_example),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_file_defective_a(shepherd_up, cli_runner, fw_empty: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--simulate",
            str(fw_empty),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_file_defective_b(shepherd_up, cli_runner, tmp_path: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--simulate",
            str(tmp_path),  # Directory
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_file_defective_c(shepherd_up, cli_runner, tmp_path: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--simulate",
            str(tmp_path / "file_abc.bin"),  # non_existing file
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_datarate_invalid_a(
    shepherd_up, cli_runner, fw_example: Path
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--datarate",
            "2000000",
            "--simulate",
            str(fw_example),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_datarate_invalid_b(
    shepherd_up, cli_runner, fw_example: Path
) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--datarate",
            "0",
            "--simulate",
            str(fw_example),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_program_target_invalid(shepherd_up, cli_runner, fw_example: Path) -> None:
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "programmer",
            "--target",
            "arduino",
            "--simulate",
            str(fw_example),
        ],
    )
    assert res.exit_code != 0


# not testable ATM (through CLI)
#   - fail pins 3x (pin_num is identical)
#   - fail wrong target (internally, fail in kModule)
#   - datasize > mem_size
