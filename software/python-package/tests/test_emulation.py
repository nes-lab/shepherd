import time
from collections.abc import Generator
from pathlib import Path

import h5py
import numpy as np
import pytest
from shepherd_core import CalibrationCape
from shepherd_core import CalibrationSeries
from shepherd_core import Reader as CoreReader
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.testbed import TargetPort
from shepherd_sheep import ShepherdDebug
from shepherd_sheep import ShepherdEmulator
from shepherd_sheep import ShepherdIOException
from shepherd_sheep import Writer
from shepherd_sheep import run_emulator
from shepherd_sheep import sysfs_interface
from shepherd_sheep.shared_memory import DataBuffer


def random_data(length: int) -> np.ndarray:
    rng = np.random.default_rng()
    return rng.integers(low=0, high=2**18, size=length, dtype="u4")


@pytest.fixture
def src_cfg() -> VirtualSourceConfig:
    here = Path(__file__).resolve()
    name = "_test_config_virtsource.yaml"
    file_path = here.parent / name
    return VirtualSourceConfig.from_file(file_path)


@pytest.fixture
def data_h5(tmp_path: Path) -> Path:
    store_path = tmp_path / "record_example.h5"
    with Writer(
        store_path,
        cal_data=CalibrationCape().harvester,
        force_overwrite=True,
    ) as store:
        store.store_hostname("Inky")
        for i in range(100):
            len_ = 10_000
            fake_data = DataBuffer(random_data(len_), random_data(len_), i)
            store.write_buffer(fake_data)
    return store_path


@pytest.fixture()
def writer(tmp_path: Path) -> Generator[Writer, None, None]:
    cal = CalibrationCape().emulator
    with Writer(
        force_overwrite=True,
        file_path=tmp_path / "test.h5",
        mode="emulator",
        cal_data=cal,
    ) as _w:
        yield _w


@pytest.fixture()
def shp_reader(data_h5: Path) -> Generator[CoreReader, None, None]:
    with CoreReader(data_h5) as _r:
        yield _r


@pytest.fixture()
def emulator(
    shepherd_up: None,
    data_h5: Path,
    src_cfg: VirtualSourceConfig,
) -> Generator[ShepherdEmulator, None, None]:
    cfg_emu = EmulationTask(
        input_path=data_h5,
        virtual_source=src_cfg,
        verbose=3,
    )
    with ShepherdEmulator(cfg_emu) as _e:
        yield _e


@pytest.mark.hardware
def test_emulation(
    writer: Writer,
    shp_reader: CoreReader,
    emulator: ShepherdEmulator,
) -> None:
    emulator.start(wait_blocking=False)
    fifo_buffer_size = sysfs_interface.get_n_buffers()
    emulator.wait_for_start(15)
    for _, dsv, dsc in shp_reader.read_buffers(start_n=fifo_buffer_size, is_raw=True):
        idx, emu_buf = emulator.get_buffer()
        writer.write_buffer(emu_buf)
        hrv_buf = DataBuffer(voltage=dsv, current=dsc)
        emulator.return_buffer(idx, hrv_buf)

    for _ in range(fifo_buffer_size):
        idx, emu_buf = emulator.get_buffer()
        writer.write_buffer(emu_buf)

    with pytest.raises(ShepherdIOException):
        _, _ = emulator.get_buffer()


@pytest.mark.hardware
def test_emulate_fn(tmp_path: Path, data_h5: Path, shepherd_up: None) -> None:
    output = tmp_path / "rec.h5"
    start_time = round(time.time() + 10)
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
        verbose=3,
    )
    run_emulator(emu_cfg)

    with h5py.File(output, "r+") as hf_emu, h5py.File(data_h5, "r") as hf_hrv:
        assert hf_emu["data"]["time"].shape[0] == hf_hrv["data"]["time"].shape[0]
        assert hf_emu["data"]["time"][0] == CalibrationSeries().time.si_to_raw(
            start_time,
        )


@pytest.mark.hardware
@pytest.mark.skip(reason="REQUIRES CAPE HARDWARE v2.4")  # real cape needed
def test_target_pins(shepherd_up: None) -> None:
    with ShepherdDebug() as shepherd_io:
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
