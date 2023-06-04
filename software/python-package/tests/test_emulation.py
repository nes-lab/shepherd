import time
from pathlib import Path

import h5py
import numpy as np
import pytest
from shepherd_core import BaseReader as ShpReader
from shepherd_core import CalibrationCape
from shepherd_core import CalibrationSeries
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models import fixtures
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.testbed import TargetPort

from shepherd import ShepherdDebug
from shepherd import ShepherdEmulator
from shepherd import ShepherdIOException
from shepherd import Writer
from shepherd import run_emulator
from shepherd import sysfs_interface
from shepherd.shared_memory import DataBuffer


def random_data(length) -> np.ndarray:
    return np.random.randint(0, high=2**18, size=length, dtype="u4")


@pytest.fixture
def src_cfg() -> VirtualSourceConfig:
    here = Path(__file__).absolute()
    name = "_test_config_virtsource.yaml"
    file_path = here.parent / name
    return VirtualSourceConfig.from_file(file_path)


@pytest.fixture
def data_h5(tmp_path: Path) -> Path:
    store_path = tmp_path / "record_example.h5"
    with Writer(store_path, cal_data=CalibrationCape().harvester) as store:
        store["hostname"] = "Inky"
        for i in range(100):
            len_ = 10_000
            fake_data = DataBuffer(random_data(len_), random_data(len_), i)
            store.write_buffer(fake_data)
    return store_path


@pytest.fixture()
def writer(tmp_path: Path):
    cal = CalibrationCape().emulator
    with Writer(
        force_overwrite=True,
        file_path=tmp_path / "test.h5",
        mode="emulator",
        cal_data=cal,
    ) as lw:
        yield lw


@pytest.fixture()
def shp_reader(data_h5: Path):
    with ShpReader(data_h5) as lr:
        yield lr


@pytest.fixture()
def emulator(
    request,
    shepherd_up,
    data_h5: Path,
    src_cfg: VirtualSourceConfig,
) -> ShepherdEmulator:
    cfg_emu = EmulationTask(
        input_path=data_h5,
        virtual_source=src_cfg,
    )
    emu = ShepherdEmulator(cfg_emu)
    request.addfinalizer(emu.__del__)
    emu.__enter__()
    request.addfinalizer(emu.__exit__)
    return emu


@pytest.mark.hardware
def test_emulation(writer, shp_reader, emulator: ShepherdEmulator) -> None:
    emulator.start(wait_blocking=False)
    fifo_buffer_size = sysfs_interface.get_n_buffers()
    emulator.wait_for_start(15)
    for _, dsv, dsc in shp_reader.read_buffers(start_n=fifo_buffer_size):
        idx, emu_buf = emulator.get_buffer()
        writer.write_buffer(emu_buf)
        hrv_buf = DataBuffer(voltage=dsv, current=dsc)
        emulator.return_buffer(idx, hrv_buf)

    for _ in range(fifo_buffer_size):
        idx, emu_buf = emulator.get_buffer()
        writer.write_buffer(emu_buf)

    with pytest.raises(ShepherdIOException):
        idx, emu_buf = emulator.get_buffer()


@pytest.mark.hardware
def test_emulate_fn(tmp_path: Path, data_h5: Path, shepherd_up) -> None:
    output = tmp_path / "rec.h5"
    start_time = round(time.time() + 10)
    fixtures.load()
    emu_cfg = EmulationTask(
        input_path=data_h5,
        output_path=output,
        duration=None,
        force_overwrite=True,
        use_cal_default=True,
        time_start=start_time,
        enable_io=True,
        io_port="A",
        pwr_port="A",
        voltage_aux=2.5,
        virtual_source=VirtualSourceConfig(name="direct"),
    )
    run_emulator(emu_cfg)

    with h5py.File(output, "r+") as hf_emu, h5py.File(data_h5, "r") as hf_hrv:
        assert hf_emu["data"]["time"].shape[0] == hf_hrv["data"]["time"].shape[0]
        assert hf_emu["data"]["time"][0] == CalibrationSeries().time.si_to_raw(
            start_time,
        )


@pytest.mark.hardware
@pytest.mark.skip(reason="REQUIRES CAPE HARDWARE v2.4")  # real cape needed
def test_target_pins(shepherd_up) -> None:
    shepherd_io = ShepherdDebug()
    shepherd_io.__enter__()
    shepherd_io.start()
    shepherd_io.select_port_for_power_tracking(TargetPort.A)

    dac_channels = [
        # combination of debug channel number, voltage_index, cal_component, cal_channel
        [1, "harvester", "dac_voltage_a", "Harvester VSimBuf"],
        [2, "harvester", "dac_voltage_b", "Harvester VMatching"],
        [4, "emulator", "dac_voltage_a", "Emulator Rail A"],
        [8, "emulator", "dac_voltage_b", "Emulator Rail B"],
    ]

    # channels: 5&6 are UART, can only be used when free, 7&8 are SWD
    gpio_channels = [0, 1, 2, 3, 4, 7, 8]
    # response: corresponding to r31_num (and later 2^num)
    pru_responses = [0, 1, 6, 7, 8, 2, 3]

    for channel in [2, 3]:
        dac_cfg = dac_channels[channel]
        value_raw = shepherd_io.convert_value_to_raw(dac_cfg[1], dac_cfg[2], 2.0)
        shepherd_io.dac_write(dac_cfg[0], value_raw)

    shepherd_io.set_io_level_converter(True)

    shepherd_io.select_port_for_io_interface(TargetPort.A)

    for io_index, io_channel in enumerate(gpio_channels):
        shepherd_io.set_gpio_one_high(io_channel)
        response = int(shepherd_io.gpi_read())
        assert response & (2 ** pru_responses[io_index])

    shepherd_io.select_port_for_io_interface(TargetPort.B)

    for io_index, io_channel in enumerate(gpio_channels):
        shepherd_io.set_gpio_one_high(io_channel)
        response = int(shepherd_io.gpi_read())
        assert response & (2 ** pru_responses[io_index])

    # TODO: could add a loopback for uart, but extra hardware is needed for that
