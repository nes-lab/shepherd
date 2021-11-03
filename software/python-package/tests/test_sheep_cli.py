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
import click
import numpy as np
from pathlib import Path

from shepherd import LogWriter
from shepherd import CalibrationData
from shepherd.shepherd_io import DataBuffer
from shepherd.cli import cli


def random_data(length):
    return np.random.randint(0, high=2 ** 18, size=length, dtype="u4")


@pytest.fixture
def data_h5(tmp_path):
    store_path = tmp_path / "record_example.h5"
    with LogWriter(store_path, CalibrationData.from_default()) as store:
        for i in range(100):
            len_ = 10_000
            fake_data = DataBuffer(random_data(len_), random_data(len_), i)
            store.write_buffer(fake_data)
    return store_path


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_record(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli, ["-vvv", "record", "-f", "-d", "10", "-o", str(store)]
    )
    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_record_no_cal(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli, ["-vvv",
              "record",
              "-d", "10",
              "--force_overwrite",
              "--default_cal",
              "-o", str(store)]
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_record_parameters_long(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    start_time = round(time.time() + 10)
    res = cli_runner.invoke(
        cli, ["-vvv",
              "record",
              "--mode", "harvesting",
              "--duration", "10",
              "--start_time", f"{start_time}",
              "--force_overwrite",
              "--default_cal",
              "--warn-only",
              "--output_path", f"{str(store)}"]
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_record_parameters_short(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    start_time = round(time.time() + 10)
    res = cli_runner.invoke(
        cli, ["-vvv",
              "record",
              "--mode", "harvesting",
              "-d", "10",
              "-s", f"{start_time}",
              "-f",
              "--no-warn-only",
              "-o", str(store)]
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_record_parameters_minimal(shepherd_up, cli_runner, tmp_path):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli, [
              "record",
              "--mode", "harvesting",
              "-f",
              "-d", "10",
              "-o", str(store)]
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_record_preconfigured(shepherd_up, cli_runner, tmp_path):
    here = Path(__file__).absolute()
    name = "example_config_harvest.yml"
    file_path = here.parent / name
    res = cli_runner.invoke(cli, ["run", "--config", f"{file_path}"])
    assert res.exit_code == 0
# TODO: also test hrv-config in ../../meta-package/

@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulate",
            "-d", "10",
            "--force_overwrite",
            "-o", str(store),
            str(data_h5),
        ],
    )

    assert res.exit_code == 0
    assert store.exists()


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_with_custom_virtsource(shepherd_up, cli_runner, tmp_path, data_h5):
    here = Path(__file__).absolute()
    name = "example_virtsource_settings.yml"
    file_path = here.parent / name
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulate",
            "-d", "10",
            "--force_overwrite",
            "--virtsource", str(file_path),
            "-o", str(store),
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
            "emulate",
            "-d", "10",
            "--force_overwrite",
            "--virtsource", "BQ25570",
            "-o", str(store),
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
    here = Path(__file__).absolute()
    name = "example_virtsource_settings.yml"
    file_path = here.parent / name
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulate",
            "-d", "10",
            "--virtWrong", str(file_path),
            "-o", str(store),
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
            "emulate",
            "-d", "10",
            "--aux_voltage", "2.5",
            "-o", str(store),
            str(data_h5),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_parameters_long(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    here = Path(__file__).absolute()
    name = "example_virtsource_settings.yml"
    file_path = here.parent / name
    start_time = round(time.time() + 10)
    res = cli_runner.invoke(
        cli,
        [
            "-vvv",
            "emulate",
            "--duration", "10",
            "--start_time", str(start_time),
            "--aux_voltage", "2.5",
            "--force_overwrite",
            "--default_cal",
            "--enable_io",
            "--io_sel_target_a",
            "--pwr_sel_target_a",
            "--warn-only",
            "--virtsource", str(file_path),
            "--output_path", str(store),
            "--uart_baudrate", "9600",
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
            "emulate",
            "-d", "10",
            "-s", str(start_time),
            "--aux_voltage", "2.5",
            "-f",
            "--disable_io",
            "--io_sel_target_b",
            "--pwr_sel_target_b",
            "--no-warn-only",
            "-o", str(store),
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
            "emulate",
            "-o", str(store),
            str(data_h5),
        ],
    )
    assert res.exit_code == 0


@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_preconfigured(shepherd_up, cli_runner, tmp_path):
    here = Path(__file__).absolute()
    name = "example_config_emulation.yml"
    file_path = here.parent / name
    res = cli_runner.invoke(cli, ["run", "--config", str(file_path)])
    assert res.exit_code == 0
# TODO: also test emu-config in ../../meta-package/

@pytest.mark.hardware
@pytest.mark.timeout(60)
def test_cli_emulate_aux_voltage_fail(shepherd_up, cli_runner, tmp_path, data_h5):
    store = tmp_path / "out.h5"
    res = cli_runner.invoke(
        cli,
        [
            "-vvv", "emulate",
            "-d", "10",
            "--aux_voltage", "5.5",
            "-o", str(store),
            str(data_h5),
        ],
    )

    assert res.exit_code != 0
