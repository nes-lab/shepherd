"""
test_sheep_cli
~~~~~
Tests the shepherd sheep CLI implemented with python click.

CAVEAT: For some reason, tests fail when invoking CLI two times within the
same test. Either find a solution or put every CLI call in a separate test.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from shepherd_core import CalibrationHarvester
from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models import PowerTracing
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask

from shepherd import Writer
from shepherd.cli import cli
from shepherd.shared_memory import DataBuffer


def random_data(length: int) -> np.ndarray:
    return np.random.randint(0, high=2**18, size=length, dtype="u4")


@pytest.fixture
def data_h5(tmp_path: Path) -> Path:
    store_path = tmp_path / "harvest_example.h5"
    with Writer(store_path, cal_data=CalibrationHarvester()) as store:
        store.store_hostname("Blinky")
        for i in range(100):
            len_ = 10_000
            fake_data = DataBuffer(random_data(len_), random_data(len_), i)
            store.write_buffer(fake_data)
    return store_path


@pytest.fixture
def path_yaml(tmp_path: Path) -> Path:
    return tmp_path / "cfg.yaml"


@pytest.fixture
def path_h5(tmp_path: Path) -> Path:
    return tmp_path / "out.h5"


@pytest.fixture
def path_here() -> Path:
    return Path(__file__).resolve().parent


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_no_cal(
    shepherd_up,
    cli_runner,
    path_yaml,
    path_h5: Path,
) -> None:
    HarvestTask(
        output_path=path_h5,
        force_overwrite=True,
        duration=10,
        use_cal_default=True,
    ).to_file(path_yaml)
    res = cli_runner.invoke(cli, ["-vvv", "task", path_yaml.as_posix()])
    assert res.exit_code == 0
    assert path_h5.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_parameters_most(
    shepherd_up,
    cli_runner,
    path_yaml,
    path_h5: Path,
) -> None:
    HarvestTask(
        output_path=path_h5,
        force_overwrite=True,
        duration=10,
        use_cal_default=True,
        time_start=datetime.fromtimestamp(round(time.time() + 10)),
        abort_on_error=False,
    ).to_file(path_yaml)
    res = cli_runner.invoke(cli, ["-vvv", "task", path_yaml.as_posix()])
    assert res.exit_code == 0
    assert path_h5.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_parameters_minimal(
    shepherd_up,
    cli_runner,
    path_yaml,
    path_h5: Path,
) -> None:
    HarvestTask(
        output_path=path_h5,
        force_overwrite=True,
        duration=10,
    ).to_file(path_yaml)
    res = cli_runner.invoke(cli, ["-vvv", "task", path_yaml.as_posix()])
    assert res.exit_code == 0
    assert path_h5.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_preconfigured(shepherd_up, cli_runner, path_here: Path) -> None:
    file_path = path_here / "_test_config_harvest.yaml"
    res = cli_runner.invoke(cli, ["task", file_path.as_posix()])
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_preconf_etc_shp_examples(
    shepherd_up,
    cli_runner,
    path_here: Path,
) -> None:
    file_path = path_here.parent / "example_config_harvest.yaml"
    res = cli_runner.invoke(cli, ["task", f"{file_path}"])
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate(
    shepherd_up,
    cli_runner,
    data_h5: Path,
    path_h5: Path,
    path_yaml: Path,
) -> None:
    EmulationTask(
        duration=10,
        force_overwrite=True,
        input_path=data_h5.as_posix(),
        output_path=path_h5.as_posix(),
        verbose=3,
    ).to_file(path_yaml)

    res = cli_runner.invoke(
        cli,
        [
            "task",
            path_yaml.as_posix(),
        ],
    )
    assert res.exit_code == 0
    assert path_h5.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_with_custom_virtsource(
    shepherd_up,
    cli_runner,
    data_h5: Path,
    path_h5: Path,
    path_yaml: Path,
    path_here: Path,
) -> None:
    EmulationTask(
        duration=10,
        force_overwrite=True,
        input_path=data_h5.as_posix(),
        output_path=path_h5.as_posix(),
        virtual_source=VirtualSourceConfig.from_file(
            path_here / "_test_config_virtsource.yaml",
        ),
        verbose=3,
    ).to_file(path_yaml)

    res = cli_runner.invoke(
        cli,
        [
            "task",
            path_yaml.as_posix(),
        ],
    )
    assert res.exit_code == 0
    assert path_h5.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_with_bq25570(
    shepherd_up,
    cli_runner,
    data_h5: Path,
    path_h5: Path,
    path_yaml: Path,
) -> None:
    EmulationTask(
        duration=10,
        force_overwrite=True,
        input_path=data_h5.as_posix(),
        output_path=path_h5.as_posix(),
        virtual_source=VirtualSourceConfig(name="BQ25570"),
        verbose=3,
    ).to_file(path_yaml)

    res = cli_runner.invoke(
        cli,
        [
            "task",
            path_yaml.as_posix(),
        ],
    )
    assert res.exit_code == 0
    assert path_h5.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_aux_voltage(
    shepherd_up,
    cli_runner,
    data_h5: Path,
    path_h5: Path,
    path_yaml: Path,
) -> None:
    EmulationTask(
        duration=10,
        force_overwrite=True,
        input_path=data_h5.as_posix(),
        output_path=path_h5.as_posix(),
        voltage_aux=2.5,
        verbose=3,
    ).to_file(path_yaml)

    res = cli_runner.invoke(
        cli,
        [
            "task",
            path_yaml.as_posix(),
        ],
    )
    assert res.exit_code == 0
    assert path_h5.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_parameters_long(
    shepherd_up,
    cli_runner,
    data_h5: Path,
    path_h5: Path,
    path_yaml: Path,
) -> None:
    EmulationTask(
        duration=10,
        force_overwrite=True,
        input_path=data_h5.as_posix(),
        output_path=path_h5.as_posix(),
        voltage_aux=2.5,
        time_start=datetime.fromtimestamp(round(time.time() + 10)),
        use_cal_default=True,
        enable_io=True,
        io_port="B",
        pwr_port="B",
        abort_on_error=False,
        gpio_tracing=GpioTracing(uart_baudrate=9600),
        power_tracing=PowerTracing(discard_current=False, discard_voltage=True),
        verbose=3,
    ).to_file(path_yaml)

    res = cli_runner.invoke(
        cli,
        [
            "task",
            path_yaml.as_posix(),
        ],
    )
    assert res.exit_code == 0
    assert path_h5.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_parameters_minimal(
    shepherd_up,
    cli_runner,
    data_h5: Path,
    path_h5: Path,
    path_yaml: Path,
) -> None:
    EmulationTask(
        input_path=data_h5.as_posix(),
        output_path=path_h5.as_posix(),
        verbose=3,
    ).to_file(path_yaml)
    res = cli_runner.invoke(
        cli,
        [
            "task",
            path_yaml.as_posix(),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_preconfigured(shepherd_up, cli_runner, path_here: Path) -> None:
    file_path = path_here / "_test_config_emulation.yaml"
    res = cli_runner.invoke(cli, ["task", file_path.as_posix()])
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(80)
def test_cli_emulate_preconf_etc_shp_examples(
    shepherd_up,
    cli_runner,
    path_here: Path,
) -> None:
    file_path = path_here.parent / "example_config_emulation.yaml"
    res = cli_runner.invoke(cli, ["task", file_path.as_posix()])
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_aux_voltage_fail(
    shepherd_up,
    cli_runner,
    data_h5: Path,
    path_h5: Path,
    path_yaml: Path,
) -> None:
    with pytest.raises(ValidationError):
        EmulationTask(
            duration=10,
            input_path=data_h5.as_posix(),
            output_path=path_h5.as_posix(),
            voltage_aux=5.5,
            verbose=3,
        ).to_file(path_yaml)
        res = cli_runner.invoke(
            cli,
            [
                "task",
                path_yaml.as_posix(),
            ],
        )
        assert res.exit_code != 0
