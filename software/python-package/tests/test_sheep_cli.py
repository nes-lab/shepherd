# -*- coding: utf-8 -*-

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
import pytest
import numpy as np
from pathlib import Path

from shepherd import LogWriter
from shepherd import CalibrationData
from shepherd.shepherd_io import DataBuffer
from shepherd.cli import cli


def random_data(length):
    return np.random.randint(0, high=2**18, size=length, dtype="u4")


@pytest.fixture
def data_h5(tmp_path):
    store_path = tmp_path / "harvest_example.h5"
    with LogWriter(store_path, CalibrationData.from_default()) as store:
        for i in range(100):
            len_ = 10_000
            fake_data = DataBuffer(random_data(len_), random_data(len_), i)
            store.write_buffer(fake_data)
    return store_path


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli, ["-vvv", "harvester", "-f", "-d", "10", "-o", str(store)]
    )
    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_no_cal(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "-d",
            "10",
            "--force_overwrite",
            "--use_cal_default",
            "-o",
            str(store),
        ],
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_parameters_long(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    start_time = round(time.time() + 10)
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "--duration",
            "10",
            "--start_time",
            f"{start_time}",
            "--force_overwrite",
            "--use_cal_default",
            "--warn-only",
            "--output_path",
            f"{str(store)}",
        ],
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_parameters_short(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    start_time = round(time.time() + 10)
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "harvester",
            "-d",
            "10",
            "-s",
            f"{start_time}",
            "-f",
            "--no-warn-only",
            "-o",
            str(store),
        ],
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_parameters_minimal(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(cli, ["harvester", "-f", "-d", "10", "-o", str(store)])

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_preconfigured(shepherd_up, cli_runner, tmp_path):
    here = Path(__file__).absolute().parent
    file_path = here / "example_config_harvester.yml"
    res = cli_runner.invoke(cli, ["run", "--config", f"{file_path}"])
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_harvest_preconf_etc_shp_examples(shepherd_up, cli_runner, tmp_path):
    here = Path(__file__).absolute().parent
    file_path = here.parent / "example_config_harvester.yml"
    res = cli_runner.invoke(cli, ["run", "--config", f"{file_path}"])
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "10",
            "--force_overwrite",
            "-o",
            str(store),
            str(data_h5),
        ],
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_with_custom_virtsource(shepherd_up, cli_runner, tmp_path, data_h5):
    here = Path(__file__).absolute().parent
    file_path = here / "example_config_virtsource.yml"
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "10",
            "--force_overwrite",
            "--virtsource",
            str(file_path),
            "-o",
            str(store),
            str(data_h5),
        ],
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_with_bq25570(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "10",
            "--force_overwrite",
            "--virtsource",
            "BQ25570",
            "-o",
            str(store),
            str(data_h5),
        ],
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_virtsource_emulate_wrong_option(
    shepherd_up, cli_runner, tmp_path, data_h5
):
    here = Path(__file__).absolute().parent
    file_path = here / "example_config_virtsource.yml"
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "10",
            "--virtWrong",
            str(file_path),
            "-o",
            str(store),
            str(data_h5),
        ],
    )
    assert res.exit_code != 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_aux_voltage(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "10",
            "--aux_voltage",
            "2.5",
            "-o",
            str(store),
            str(data_h5),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_parameters_long(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    here = Path(__file__).absolute().parent
    file_path = here / "example_config_virtsource.yml"
    start_time = round(time.time() + 10)
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "--duration",
            "10",
            "--start_time",
            str(start_time),
            "--aux_voltage",
            "2.5",
            "--force_overwrite",
            "--use_cal_default",
            "--enable_io",
            "--io_sel_target_a",
            "--pwr_sel_target_a",
            "--warn-only",
            "--virtsource",
            str(file_path),
            "--output_path",
            str(store),
            "--uart_baudrate",
            "9600",
            "--log_mid_voltage",
            "--skip_log_voltage",
            "--skip_log_current",
            "--skip_log_gpio",
            str(data_h5),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_parameters_short(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    start_time = round(time.time() + 10)
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "10",
            "-s",
            str(start_time),
            "--aux_voltage",
            "2.5",
            "-f",
            "--disable_io",
            "--io_sel_target_b",
            "--pwr_sel_target_b",
            "--no-warn-only",
            "-o",
            str(store),
            str(data_h5),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_parameters_minimal(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "emulator",
            "-o",
            str(store),
            str(data_h5),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_preconfigured(shepherd_up, cli_runner, tmp_path):
    here = Path(__file__).absolute().parent
    file_path = here / "example_config_emulator.yml"
    res = cli_runner.invoke(cli, ["run", "--config", str(file_path)])
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_preconf_etc_shp_examples(shepherd_up, cli_runner, tmp_path):
    here = Path(__file__).absolute().parent
    file_path = here.parent / "example_config_emulator.yml"
    res = cli_runner.invoke(cli, ["run", "--config", str(file_path)])
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_aux_voltage_fail(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulator",
            "-d",
            "10",
            "--aux_voltage",
            "5.5",
            "-o",
            str(store),
            str(data_h5),
        ],
    )
    assert res.exit_code != 0
