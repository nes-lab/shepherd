"""Benchmark for preparing input-buffers (h5-file -> ram -> PRU).

Results on beaglebone 2026-10-08

        numpy_ndarray_len(iv_hrv_mem) = 0.114 s for 10000 reps
        numpy_ndarray_shape0(iv_hrv_mem) = 0.161 s for 10000 reps
        mem_inp_write_iv_v1(iv_hrv_mem, None) = 0.148 s for 10000 reps
        mem_inp_write_iv_v2(iv_hrv_mem, None) = 0.148 s for 10000 reps
        mem_inp_write_iv_v3(iv_hrv_mem, None) = 0.032 s for 10000 reps
        mem_inp_write_iv_v1(iv_trace_si, cal_data) = 9.347 s for 200 reps
        mem_inp_write_iv_v2(iv_trace_si, cal_data) = 9.502 s for 200 reps
        mem_inp_write_iv_v3(iv_trace_si, cal_data) = 9.521 s for 200 reps
        mem_inp_write_iv_v1(iv_trace_raw, None) = 1.433 s for 200 reps
        mem_inp_write_iv_v2(iv_trace_raw, None) = 1.431 s for 200 reps
        mem_inp_write_iv_v3(iv_trace_raw, None) = 1.433 s for 200 reps

Learning
- len(ndarray) is faster than ndarray.shape[0]
- we should use pre-computed harvesting-files (skips scaling and restructuring)
- the methods itself have minimal influence

"""

import time
from timeit import timeit

import numpy as np
from shepherd_core.data_models.base.calibration import CalibrationPair
from shepherd_core.data_models.base.calibration import CalibrationSeries
from shepherd_core.logger import log
from shepherd_sheep.logger import set_verbosity
from shepherd_sheep.shared_mem_iv_input import IVTrace


def mem_inp_write_iv_v1(
    data: IVTrace | np.ndarray,
    cal: CalibrationSeries | None,
) -> np.ndarray:
    len_data = len(data)
    if isinstance(data, IVTrace):
        # transform raw ADC data to SI-Units
        # -> the virtual-source-emulator in PRU expects uV and nV
        if cal:
            # option to disable scaling here if already done (performance improvement)
            data.ds_voltage = cal.voltage.raw_to_si(data.ds_voltage).astype(np.uint32)
            data.ds_current = cal.current.raw_to_si(data.ds_current).astype(np.uint32)
        # interweave data (voltage | current in parallel)
        iv_data = np.empty((2 * len_data,), dtype=data.ds_voltage.dtype)
        iv_data[0::2] = data.ds_voltage[:len_data]
        iv_data[1::2] = data.ds_current[:len_data]
    else:
        iv_data = data.reshape((2 * len_data, 1), order="C")
    return iv_data


def mem_inp_write_iv_v2(
    data: IVTrace | np.ndarray,
    cal: CalibrationSeries | None,
) -> np.ndarray:
    len_data = len(data)
    if isinstance(data, IVTrace):
        iv_data = np.empty((2 * len_data,), dtype=data.ds_voltage.dtype)
        if cal:
            iv_data[0::2] = cal.voltage.raw_to_si(data.ds_voltage).astype(np.uint32)
            iv_data[1::2] = cal.current.raw_to_si(data.ds_current).astype(np.uint32)
        else:
            # interweave data (voltage | current in parallel)
            iv_data[0::2] = data.ds_voltage[:len_data]
            iv_data[1::2] = data.ds_current[:len_data]
    else:
        iv_data = data.reshape((2 * len_data, 1), order="C")
    return iv_data


def mem_inp_write_iv_v3(
    data: IVTrace | np.ndarray,
    cal: CalibrationSeries | None,
) -> np.ndarray:
    len_data = len(data)
    if isinstance(data, IVTrace):
        iv_data = np.empty((len_data, 2), dtype=data.ds_voltage.dtype)
        if cal:
            iv_data[:, 0] = cal.voltage.raw_to_si(data.ds_voltage).astype(np.uint32)
            iv_data[:, 1] = cal.current.raw_to_si(data.ds_current).astype(np.uint32)
        else:
            # interweave data (voltage | current in parallel)
            iv_data[:, 0] = data.ds_voltage[:len_data]
            iv_data[:, 1] = data.ds_current[:len_data]
    else:
        iv_data = data
    return iv_data


def numpy_ndarray_len(data: np.ndarray) -> bool:
    cut_position = 12345
    return len(data[:cut_position]) + len(data[cut_position:]) > len(data)


def numpy_ndarray_shape0(data: np.ndarray) -> bool:
    cut_position = 12345
    return data[:cut_position].shape[0] + data[cut_position:].shape[0] > data.shape[0]


if __name__ == "__main__":
    set_verbosity()

    cal_data = CalibrationSeries(
        # sheep can skip scaling if cal is ideal (applied here)
        voltage=CalibrationPair(gain=1e-6, offset=0),
        current=CalibrationPair(gain=1e-9, offset=0),
    )

    rng = np.random.default_rng()
    iv_trace_si = IVTrace(
        voltage=rng.uniform(low=1.0, high=3.0, size=100_000),
        current=rng.uniform(low=0.001, high=0.05, size=100_000),
    )
    iv_trace_raw = IVTrace(
        voltage=rng.integers(low=0, high=2**18, size=100_000, dtype=np.uint32),
        current=rng.integers(low=0, high=2**18, size=100_000, dtype=np.uint32),
    )
    iv_hrv_mem = np.empty((100_000, 2), dtype=np.uint32)
    iv_hrv_mem[:, 0] = rng.integers(low=0, high=2**18, size=100_000, dtype=np.uint32)
    iv_hrv_mem[:, 1] = rng.integers(low=0, high=2**18, size=100_000, dtype=np.uint32)

    repetitions = 10000
    for routine_under_test in [
        "numpy_ndarray_len(iv_hrv_mem)",
        "numpy_ndarray_shape0(iv_hrv_mem)",
        "mem_inp_write_iv_v1(iv_hrv_mem, None)",
        "mem_inp_write_iv_v2(iv_hrv_mem, None)",
        "mem_inp_write_iv_v3(iv_hrv_mem, None)",
    ]:
        time.sleep(1)
        time_total = timeit(
            routine_under_test,
            globals=globals(),
            number=repetitions,
        )
        log.info("\t%s = %.3f s for %d reps", routine_under_test, time_total, repetitions)

    repetitions = 200
    for _args in ["iv_trace_si, cal_data", "iv_trace_raw, None"]:
        for routine_under_test in [
            f"mem_inp_write_iv_v1({_args})",
            f"mem_inp_write_iv_v2({_args})",
            f"mem_inp_write_iv_v3({_args})",
        ]:
            time.sleep(1)
            time_total = timeit(
                routine_under_test,
                globals=globals(),
                number=repetitions,
            )
            log.info("\t%s = %.3f s for %d reps", routine_under_test, time_total, repetitions)
