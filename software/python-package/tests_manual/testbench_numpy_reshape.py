"""Benchmark for Resampling of emu-output.

Warning: default .mean() uses float64, which causes
         a panic on the beaglebone (system halts randomly)

Prepare Input       11.54it/s
u32-Reshape         79.84it/s
Reshape-u32         82.23it/s
Reshape-Copy-u32    24.48it/s
Reshape-u64         31.31it/s -> no difference to version with clip and recast
Reshape-Copy-u64    16.11it/s
Slicer              34652.21it/s

"""

import time
from timeit import timeit

import numpy as np
from shepherd_core.data_models.base.calibration import CalibrationPair
from shepherd_core.data_models.base.calibration import CalibrationSeries
from shepherd_core.logger import log
from shepherd_sheep.logger import set_verbosity
from shepherd_sheep.shared_mem_iv_input import IVTrace
from tqdm import tqdm


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
            data.voltage = cal.voltage.raw_to_si(data.voltage).astype(np.uint32)
            data.current = cal.current.raw_to_si(data.current).astype(np.uint32)
        # interweave data (voltage | current in parallel)
        iv_data = np.empty((2 * len_data,), dtype=data.voltage.dtype)
        iv_data[0::2] = data.voltage[:len_data]
        iv_data[1::2] = data.current[:len_data]
    else:
        iv_data = data.reshape((2 * len_data, 1), order="C")
    return iv_data


def mem_inp_write_iv_v2(
    data: IVTrace | np.ndarray,
    cal: CalibrationSeries | None,
) -> np.ndarray:
    len_data = len(data)
    if isinstance(data, IVTrace):
        iv_data = np.empty((2 * len_data,), dtype=data.voltage.dtype)
        if cal:
            iv_data[0::2] = cal.voltage.raw_to_si(data.voltage).astype(np.uint32)
            iv_data[1::2] = cal.current.raw_to_si(data.current).astype(np.uint32)
        else:
            # interweave data (voltage | current in parallel)
            iv_data[0::2] = data.voltage[:len_data]
            iv_data[1::2] = data.current[:len_data]
    else:
        iv_data = data.reshape((2 * len_data, 1), order="C")
    return iv_data


def mem_inp_write_iv_v3(
    data: IVTrace | np.ndarray,
    cal: CalibrationSeries | None,
) -> np.ndarray:
    len_data = len(data)
    if isinstance(data, IVTrace):
        iv_data = np.empty((len_data, 2), dtype=data.voltage.dtype)
        if cal:
            iv_data[:, 0] = cal.voltage.raw_to_si(data.voltage).astype(np.uint32)
            iv_data[:, 1] = cal.current.raw_to_si(data.current).astype(np.uint32)
        else:
            # interweave data (voltage | current in parallel)
            iv_data[:, 0] = data.voltage[:len_data]
            iv_data[:, 1] = data.current[:len_data]
    else:
        iv_data = data
    return iv_data


def mem_inp_len_v1(data: np.ndarray) -> bool:
    cut_position = 12345
    return len(data[:cut_position]) + len(data[cut_position:]) > len(data)


def mem_inp_len_v2(data: np.ndarray) -> bool:
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
        "mem_inp_len_v1(iv_hrv_mem)",
        "mem_inp_len_v2(iv_hrv_mem)",
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
    for _args in ["iv_trace_si, cal_data", "iv_trace_raw, None", "iv_hrv_mem, None"]:
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


exit()

rng = np.random.default_rng()

reduction_factor = 100
iterations = 80

data = [
    rng.integers(low=0, high=2**18, size=100_000, dtype=np.uint32)
    for _ in tqdm(range(iterations), desc="Prepare Input")
]

for i in tqdm(range(iterations), desc="u32-Reshape"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = data[i][0:len_add2].reshape(len_new, reduction_factor).mean(axis=1, dtype=np.uint32)
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Reshape-u32"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = np.reshape(data[i][0:len_add2], (len_new, reduction_factor)).mean(
        axis=1, dtype=np.uint32
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)

for i in tqdm(range(iterations), desc="Reshape-Copy-u32"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = np.reshape(data[i][0:len_add2], (len_new, reduction_factor), copy=True).mean(
        axis=1, dtype=np.uint32
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Reshape-u64"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = np.reshape(data[i][0:len_add2], (len_new, reduction_factor)).mean(
        axis=1, dtype=np.uint64
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Reshape-u64-Final"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = (
        data[i][0:len_add2]
        .reshape(len_new, reduction_factor)
        .mean(axis=1, dtype=np.uint64)
        .clip(0, 2**32)
        .astype(np.uint32)
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Reshape-Copy-u64"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = np.reshape(data[i][0:len_add2], (len_new, reduction_factor), copy=True).mean(
        axis=1, dtype=np.uint64
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Slicer"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = data[i][0:len_add2:reduction_factor]  # .copy()
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)
