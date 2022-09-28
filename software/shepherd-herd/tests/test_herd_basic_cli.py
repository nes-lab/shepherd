import pytest
from shepherd_herd import cli

from .conftest import extract_first_sheep


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
            f"{sheep}," "-vvv",
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


# TODO: test providing user and key filename
# TODO: test poweroff (reboot)
# TODO: test sudo
