import time
from itertools import product
from pathlib import Path

import h5py
import numpy as np
import pytest
from shepherd_core import BaseReader as ShpReader
from shepherd_core import CalibrationCape
from shepherd_core import CalibrationHarvester

from shepherd import LogWriter
from shepherd.datalog import ExceptionRecord
from shepherd.shared_memory import DataBuffer


def random_data(length: int) -> np.ndarray:
    return np.random.randint(0, high=2**18, size=length, dtype="u4")


@pytest.fixture()
def data_buffer() -> DataBuffer:
    len_ = 10_000
    voltage = random_data(len_)
    current = random_data(len_)
    data = DataBuffer(voltage, current, 1551848387472)
    return data


@pytest.fixture
def data_h5(tmp_path: Path) -> Path:
    name = tmp_path / "record_example.h5"
    with LogWriter(name, CalibrationHarvester()) as store:
        store["hostname"] = "Pinky"
        for i in range(100):
            len_ = 10_000
            fake_data = DataBuffer(random_data(len_), random_data(len_), i)
            store.write_buffer(fake_data)
    return name


@pytest.fixture
def cal_cape() -> CalibrationCape:
    return CalibrationCape()


@pytest.mark.parametrize("mode", ["harvester"])
def test_create_logwriter(mode, tmp_path: Path, cal_cape: CalibrationCape) -> None:
    d = tmp_path / f"{ mode }.h5"
    h = LogWriter(file_path=d, cal_=cal_cape[mode], mode=mode)
    assert not d.exists()
    h.__enter__()
    assert d.exists()
    h.__exit__()


def test_create_logwriter_with_force(tmp_path: Path, cal_cape: CalibrationCape) -> None:
    d = tmp_path / "harvest.h5"
    d.touch()
    stat = d.stat()
    time.sleep(0.1)

    h = LogWriter(file_path=d, cal_=cal_cape.harvester, force_overwrite=False)
    h.__enter__()
    h.__exit__()
    # This should have created the following alternative file:
    d_altered = tmp_path / "harvest.0.h5"
    assert h.store_path == d_altered
    assert d_altered.exists()

    h = LogWriter(file_path=d, cal_=cal_cape.harvester, force_overwrite=True)
    h.__enter__()
    h.__exit__()
    new_stat = d.stat()
    assert new_stat.st_mtime > stat.st_mtime


@pytest.mark.parametrize("mode", ["harvester"])
def test_logwriter_data(
    mode, tmp_path: Path, data_buffer, cal_cape: CalibrationCape
) -> None:
    d = tmp_path / "harvest.h5"
    with LogWriter(file_path=d, cal_=cal_cape.harvester, mode=mode) as log:
        log.write_buffer(data_buffer)

    with h5py.File(d, "r") as written:
        assert "data" in written
        assert "time" in written["data"]
        for variable in ["voltage", "current"]:
            assert variable in written["data"]  # .keys()
            ref_var = getattr(data_buffer, variable)
            assert all(written["data"][variable][:] == ref_var)


@pytest.mark.parametrize("mode", ["harvester"])
def test_calibration_logging(mode, tmp_path: Path, cal_cape: CalibrationCape) -> None:
    d = tmp_path / "recording.h5"
    with LogWriter(file_path=d, mode=mode, cal_=cal_cape.harvester) as _:
        pass

    h5store = h5py.File(d, "r")
    # hint: shpReader would be more direct, but less untouched

    for channel_entry, parameter in product(
        ["voltage", "current", "time"],
        ["gain", "offset"],
    ):
        assert (
            h5store["data"][channel_entry[0]].attrs[parameter]
            == cal_cape[mode][channel_entry[1]][parameter]
        )


def test_exception_logging(
    tmp_path: Path, data_buffer: DataBuffer, cal_cape: CalibrationCape
) -> None:
    d = tmp_path / "harvest.h5"

    with LogWriter(file_path=d, cal_=cal_cape.harvester) as writer:
        writer.write_buffer(data_buffer)

        ts = int(time.time() * 1000)
        writer.write_exception(ExceptionRecord(ts, "there was an exception", 0))
        writer.write_exception(
            ExceptionRecord(ts + 1, "there was another exception", 1),
        )

        # Note: decode is needed at least for h5py < 3, and old dtype=h5py.special_dtype(vlen=str)
        if isinstance(writer.xcpt_grp["message"][0], str):
            assert writer.xcpt_grp["message"][0] == "there was an exception"
            assert writer.xcpt_grp["message"][1] == "there was another exception"
        else:
            assert (
                writer.xcpt_grp["message"][0].decode("UTF8") == "there was an exception"
            )
            assert (
                writer.xcpt_grp["message"][1].decode("UTF8")
                == "there was another exception"
            )
        assert writer.xcpt_grp["value"][0] == 0
        assert writer.xcpt_grp["value"][1] == 1
        assert writer.xcpt_grp["time"][0] == ts
        assert writer.xcpt_grp["time"][1] == ts + 1


def test_key_value_store(tmp_path: Path, cal_cape: CalibrationCape) -> None:
    d = tmp_path / "harvest.h5"

    with LogWriter(file_path=d, cal_=cal_cape.harvester) as writer:
        writer["some string"] = "this is a string"
        writer["some value"] = 5

    with h5py.File(d, "r+") as hf:
        assert hf.attrs["some value"] == 5
        assert hf.attrs["some string"] == "this is a string"


@pytest.mark.timeout(2)
def test_logwriter_performance(
    tmp_path: Path, data_buffer: DataBuffer, cal_cape: CalibrationCape
) -> None:
    d = tmp_path / "harvest_perf.h5"
    with LogWriter(
        file_path=d,
        force_overwrite=True,
        cal_=cal_cape.harvester,
    ) as log:
        log.write_buffer(data_buffer)


def test_reader_performance(data_h5: Path) -> None:
    read_durations = []
    with ShpReader(file_path=data_h5) as reader:
        past = time.time()
        for _ in reader.read_buffers():
            now = time.time()
            elapsed = now - past
            read_durations.append(elapsed)
            past = time.time()
    assert np.mean(read_durations) < 0.05
