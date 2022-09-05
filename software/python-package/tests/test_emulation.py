import pytest
from pathlib import Path
import numpy as np
import h5py
import time
import yaml

from shepherd.datalog_reader import LogReader as ShpReader
from shepherd.shepherd_io import DataBuffer, VirtualSourceConfig

from shepherd import ShepherdDebug
from shepherd import LogWriter
from shepherd import Emulator
from shepherd import run_emulator
from shepherd import sysfs_interface
from shepherd import CalibrationData
from shepherd import ShepherdIOException


def random_data(length):
    return np.random.randint(0, high=2**18, size=length, dtype="u4")


@pytest.fixture
def virtsource_settings_yml():
    here = Path(__file__).absolute()
    name = "example_config_virtsource.yml"
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
    cal = CalibrationData.from_default()
    with LogWriter(
        force_overwrite=True,
        file_path=tmp_path / "test.h5",
        mode="emulator",
        calibration_data=cal,
    ) as lw:
        yield lw


@pytest.fixture()
def shp_reader(data_h5):
    with ShpReader(data_h5) as lr:
        yield lr


@pytest.fixture()
def emulator(request, shepherd_up, shp_reader, virtsource_settings_yml):
    vs_cfg = VirtualSourceConfig(virtsource_settings_yml)
    fifo_buffer_size = sysfs_interface.get_n_buffers()
    init_buffers = [
        DataBuffer(voltage=dsv, current=dsc)
        for _, dsv, dsc in shp_reader.read_buffers(end_n=fifo_buffer_size)
    ]
    emu = Emulator(
        calibration_recording=CalibrationData(shp_reader.get_calibration_data()),
        calibration_emulator=CalibrationData.from_default(),
        initial_buffers=init_buffers,
        vsource=vs_cfg,
    )
    request.addfinalizer(emu.__del__)
    emu.__enter__()
    request.addfinalizer(emu.__exit__)
    return emu


@pytest.mark.hardware
def test_emulation(log_writer, shp_reader, emulator):
    emulator.start(wait_blocking=False)
    fifo_buffer_size = sysfs_interface.get_n_buffers()
    emulator.wait_for_start(15)
    for _, dsv, dsc in shp_reader.read_buffers(start_n=fifo_buffer_size):
        idx, emu_buf = emulator.get_buffer()
        log_writer.write_buffer(emu_buf)
        hrvst_buf = DataBuffer(voltage=dsv, current=dsc)
        emulator.return_buffer(idx, hrvst_buf)

    for _ in range(fifo_buffer_size):
        idx, emu_buf = emulator.get_buffer()
        log_writer.write_buffer(emu_buf)

    with pytest.raises(ShepherdIOException):
        idx, emu_buf = emulator.get_buffer()


@pytest.mark.hardware
def test_emulate_fn(tmp_path, data_h5, shepherd_up):
    output = tmp_path / "rec.h5"
    start_time = round(time.time() + 10)
    run_emulator(
        input_path=data_h5,
        output_path=output,
        duration=None,
        force_overwrite=True,
        use_cal_default=True,
        start_time=start_time,
        set_target_io_lvl_conv=True,
        sel_target_for_io=True,
        sel_target_for_pwr=True,
        aux_target_voltage=2.5,
        virtsource="direct",
    )

    with h5py.File(output, "r+") as hf_emu, h5py.File(data_h5) as hf_hrvst:
        assert hf_emu["data"]["time"].shape[0] == hf_hrvst["data"]["time"].shape[0]
        assert hf_emu["data"]["time"][0] == start_time * 10**9


@pytest.mark.hardware
def test_target_pins(shepherd_up):
    shepherd_io = ShepherdDebug()
    shepherd_io.__enter__()
    shepherd_io.start()
    shepherd_io.select_main_target_for_power(sel_target_a=True)

    dac_channels = [
        # combination of debug channel number, voltage_index, cal_component, cal_channel
        [1, "harvester", "dac_voltage_a", "Harvester VSimBuf"],
        [2, "harvester", "dac_voltage_b", "Harvester VMatching"],
        [4, "emulator", "dac_voltage_a", "Emulator Rail A"],
        [8, "emulator", "dac_voltage_b", "Emulator Rail B"],
    ]

    # channels: 5&6 are UART, can only be used when free, 7&8 are SWD
    gpio_channels = [
        0,
        1,
        2,
        3,
        4,
        7,
        8,
    ]
    # response: corresponding to r31_num (and later 2^num)
    pru_responses = [
        0,
        1,
        6,
        7,
        8,
        2,
        3,
    ]

    for channel in [2, 3]:
        dac_cfg = dac_channels[channel]
        value_raw = shepherd_io.convert_value_to_raw(dac_cfg[1], dac_cfg[2], 2.0)
        shepherd_io.dac_write(dac_cfg[0], value_raw)

    shepherd_io.set_target_io_level_conv(True)

    shepherd_io.select_main_target_for_io(sel_target_a=True)

    for io_index, io_channel in enumerate(gpio_channels):
        shepherd_io.set_gpio_one_high(io_channel)
        response = int(shepherd_io.gpi_read())
        assert response & (2 ** pru_responses[io_index])

    shepherd_io.select_main_target_for_io(sel_target_a=False)

    for io_index, io_channel in enumerate(gpio_channels):
        shepherd_io.set_gpio_one_high(io_channel)
        response = int(shepherd_io.gpi_read())
        assert response & (2 ** pru_responses[io_index])

    # TODO: could add a loopback for uart, but extra hardware is needed for that
