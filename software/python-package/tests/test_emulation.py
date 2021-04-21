import pytest
from pathlib import Path
import numpy as np
import h5py
import time
import yaml

from shepherd.shepherd_io import DataBuffer, VirtualSourceData

from shepherd import LogWriter
from shepherd import LogReader
from shepherd import Emulator
from shepherd import emulate
from shepherd import CalibrationData
from shepherd import ShepherdIOException


def random_data(len):
    return np.random.randint(0, high=2 ** 18, size=len, dtype="u4")


@pytest.fixture
def virtsource_settings_yml():
    here = Path(__file__).absolute()
    name = "example_virtsource_settings.yml"
    file_path = here.parent / name
    with open(file_path, "r") as config_data:
        full_config = yaml.safe_load(config_data)
    return full_config["virtsource"]


@pytest.fixture
def data_h5(tmp_path):
    store_path = tmp_path / "record_example.h5"
    with LogWriter(store_path, CalibrationData.from_default()) as store:
        for i in range(100):
            len_ = 10_000
            fake_data = DataBuffer(random_data(len_), random_data(len_), i)
            store.write_buffer(fake_data)
    return store_path


@pytest.fixture()
def log_writer(tmp_path):
    calib = CalibrationData.from_default()
    with LogWriter(
        force_overwrite=True,
        store_path=tmp_path / "test.h5",
        mode="emulation",
        calibration_data=calib,
    ) as lw:
        yield lw


@pytest.fixture()
def log_reader(data_h5):
    with LogReader(data_h5, 10_000) as lr:
        yield lr


@pytest.fixture()
def emulator(request, shepherd_up, log_reader):
    emu = Emulator(
        calibration_recording=log_reader.get_calibration_data(),
        calibration_emulation=CalibrationData.from_default(),
        initial_buffers=log_reader.read_buffers(end=64),
    )
    request.addfinalizer(emu.__del__)
    emu.__enter__()
    request.addfinalizer(emu.__exit__)
    return emu


@pytest.fixture()
def virtsource_emulator(request, shepherd_up, log_reader, virtsource_settings_yml):
    vs_settings = VirtualSourceData(virtsource_settings_yml)
    emu = Emulator(
        calibration_recording=log_reader.get_calibration_data(),
        calibration_emulation=CalibrationData.from_default(),
        initial_buffers=log_reader.read_buffers(end=64),
        settings_virtsource=vs_settings,
    )
    request.addfinalizer(emu.__del__)
    emu.__enter__()
    request.addfinalizer(emu.__exit__)
    return emu


@pytest.mark.hardware
def test_emulation(log_writer, log_reader, emulator):

    emulator.start(wait_blocking=False)
    emulator.wait_for_start(15)
    for hrvst_buf in log_reader.read_buffers(start=64):
        idx, emu_buf = emulator.get_buffer(timeout=1)
        log_writer.write_buffer(emu_buf)
        emulator.return_buffer(idx, hrvst_buf)

    for _ in range(64):
        idx, emu_buf = emulator.get_buffer(timeout=1)
        log_writer.write_buffer(emu_buf)

    with pytest.raises(ShepherdIOException):
        idx, emu_buf = emulator.get_buffer(timeout=1)


@pytest.mark.hardware
def test_virtsource_emulation(log_writer, log_reader, virtsource_emulator):

    virtsource_emulator.start(wait_blocking=False)
    virtsource_emulator.wait_for_start(15)
    for hrvst_buf in log_reader.read_buffers(start=64):
        idx, emu_buf = virtsource_emulator.get_buffer(timeout=1)
        log_writer.write_buffer(emu_buf)
        virtsource_emulator.return_buffer(idx, hrvst_buf)

    for _ in range(64):
        idx, emu_buf = virtsource_emulator.get_buffer(timeout=1)
        log_writer.write_buffer(emu_buf)

    with pytest.raises(ShepherdIOException):
        idx, emu_buf = virtsource_emulator.get_buffer(timeout=1)


@pytest.mark.hardware
def test_emulate_fn(tmp_path, data_h5, shepherd_up):
    output = tmp_path / "rec.h5"
    start_time = int(time.time() + 15)
    emulate(
        input_path=data_h5,
        output_path=output,
        duration=None,
        force_overwrite=True,
        no_calib=True,
        start_time=start_time,
        set_target_io_lvl_conv=True,
        sel_target_for_io=True,
        sel_target_for_pwr=True,
        aux_target_voltage=2.5,
    )

    with h5py.File(output, "r+") as hf_emu, h5py.File(data_h5) as hf_hrvst:
        assert (
            hf_emu["data"]["time"].shape[0]
            == hf_hrvst["data"]["time"].shape[0]
        )
        assert hf_emu["data"]["time"][0] == start_time * 10**9
