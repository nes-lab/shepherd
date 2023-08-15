import time
from pathlib import Path

import h5py
import numpy as np
import pytest
from shepherd_core import CalibrationHarvester
from shepherd_core.data_models.task import HarvestTask
from shepherd_sheep import ShepherdHarvester
from shepherd_sheep import Writer
from shepherd_sheep import run_harvester


@pytest.fixture(params=["harvester"])  # TODO: there is a second mode now
def mode(request) -> str:
    return request.param


@pytest.fixture()
def writer(tmp_path: Path, mode: str):
    with Writer(
        mode=mode,
        cal_data=CalibrationHarvester(),
        force_overwrite=True,
        file_path=tmp_path / "test.h5",
    ) as lw:
        yield lw


@pytest.fixture()
def harvester(request, shepherd_up, mode: str, tmp_path: Path) -> ShepherdHarvester:
    cfg = HarvestTask(output_path=tmp_path / "hrv_123.h5")
    rec = ShepherdHarvester(cfg=cfg, mode=mode)
    request.addfinalizer(rec.__del__)
    rec.__enter__()
    request.addfinalizer(rec.__exit__)
    return rec


@pytest.mark.hardware
def test_instantiation(shepherd_up, tmp_path: Path) -> None:
    cfg = HarvestTask(output_path=tmp_path / "hrv_123.h5")
    rec = ShepherdHarvester(cfg)
    rec.__enter__()
    assert rec is not None
    rec.__exit__()
    del rec


@pytest.mark.hardware
def test_harvester(writer, harvester: ShepherdHarvester) -> None:
    harvester.start(wait_blocking=False)
    harvester.wait_for_start(15)

    for _ in range(100):
        idx, buf = harvester.get_buffer()
        writer.write_buffer(buf)
        harvester.return_buffer(idx)


@pytest.mark.hardware  # TODO extend with new harvester-options
@pytest.mark.timeout(40)
def test_harvester_fn(tmp_path, shepherd_up) -> None:
    path = tmp_path / "rec.h5"
    time_start = int(time.time() + 10)
    cfg = HarvestTask(
        output_path=path,
        time_start=time_start,
        duration=10,
        force_overwrite=True,
        use_cal_default=True,
    )
    run_harvester(cfg)

    with h5py.File(path, "r+") as hf:
        n_samples = hf["data"]["time"].shape[0]
        assert 900_000 < n_samples <= 1_100_000
        assert hf["data"]["time"][0] == time_start * 10**9
        # test for equidistant timestamps
        time_series = hf["data"]["time"]
        diff_series = time_series[1:] - time_series[:-1]
        unique = np.unique(diff_series)
        assert len(unique) == 1
