import time

import h5py
import numpy as np
import pytest
from shepherd_core import CalibrationHarvester

from shepherd import Writer
from shepherd import ShepherdHarvester
from shepherd import run_harvester


@pytest.fixture(params=["harvester"])  # TODO: there is a second mode now
def mode(request):
    return request.param


@pytest.fixture()
def log_writer(tmp_path, mode):
    with Writer(
        mode=mode,
        cal_data=CalibrationHarvester(),
        force_overwrite=True,
        file_path=tmp_path / "test.h5",
    ) as lw:
        yield lw


@pytest.fixture()
def harvester(request, shepherd_up, mode) -> ShepherdHarvester:
    rec = ShepherdHarvester(shepherd_mode=mode)
    request.addfinalizer(rec.__del__)
    rec.__enter__()
    request.addfinalizer(rec.__exit__)
    return rec


@pytest.mark.hardware
def test_instantiation(shepherd_up) -> None:
    rec = ShepherdHarvester()
    rec.__enter__()
    assert rec is not None
    rec.__exit__()
    del rec


@pytest.mark.hardware
def test_harvester(log_writer, harvester: ShepherdHarvester) -> None:
    harvester.start(wait_blocking=False)
    harvester.wait_for_start(15)

    for _ in range(100):
        idx, buf = harvester.get_buffer()
        log_writer.write_buffer(buf)
        harvester.return_buffer(idx)


@pytest.mark.hardware  # TODO extend with new harvester-options
@pytest.mark.timeout(40)
def test_harvester_fn(tmp_path, shepherd_up) -> None:
    output = tmp_path / "rec.h5"
    start_time = int(time.time() + 10)
    run_harvester(
        output_path=output,
        duration=10,
        force_overwrite=True,
        use_cal_default=True,
        start_time=start_time,
    )

    with h5py.File(output, "r+") as hf:
        n_samples = hf["data"]["time"].shape[0]
        assert 900_000 < n_samples <= 1_100_000
        assert hf["data"]["time"][0] == start_time * 10**9
        # test for equidistant timestamps
        time_series = hf["data"]["time"]
        diff_series = time_series[1:] - time_series[:-1]
        unique = np.unique(diff_series)
        assert len(unique) == 1
