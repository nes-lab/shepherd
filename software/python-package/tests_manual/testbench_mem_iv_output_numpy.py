"""Benchmark for preparing output-files (PRU -> ram -> hdf5-file).

Results on beaglebone 2026-10-08


Learning


"""

import time
from timeit import timeit

import numpy as np
from shepherd_core.data_models.base.calibration import CalibrationPair
from shepherd_core.data_models.base.calibration import CalibrationSeries
from shepherd_core.logger import log
from shepherd_sheep.logger import set_verbosity
from shepherd_sheep.shared_mem_iv_input import IVTrace

cal_data = CalibrationSeries(
    # sheep can skip scaling if cal is ideal (applied here)
    voltage=CalibrationPair(gain=1e-6, offset=0),
    current=CalibrationPair(gain=1e-9, offset=0),
)
gain: float = 1e-9  # nW
offset_V_raw = int(cal_data.voltage.offset / cal_data.voltage.gain)
offset_C_raw = int(cal_data.current.offset / cal_data.current.gain)
gain_P_nW = cal_data.voltage.gain * cal_data.current.gain / gain


def mem_out_iv_reduce_v1(
    data: IVTrace | np.ndarray,
    reduction_factor: int,
) -> np.ndarray:
    len_add = len(data)
    len_red = len_add // reduction_factor
    len_add = len_red * reduction_factor

    data.ds_voltage = (
        data.ds_voltage[:len_add]
        .reshape(len_red, reduction_factor)
        .mean(axis=1, dtype=np.uint64)
        .clip(0, 2**32 - 1)
        .astype(np.uint32)
    )
    data.ds_current = (
        data.ds_current[:len_add]
        .reshape(len_red, reduction_factor)
        .mean(axis=1, dtype=np.uint64)
        .clip(0, 2**32 - 1)
        .astype(np.uint32)
    )
    return data


def mem_out_power_v1(data: IVTrace | np.ndarray) -> np.ndarray:
    len_add = len(data)
    V_ = data.ds_voltage[:len_add].clip(0, 2 ** 18 - 1).astype(np.int64) + offset_V_raw
    C_ = data.ds_current[:len_add].clip(0, 2 ** 18 - 1).astype(np.int64) + offset_C_raw
    power = ((V_ * C_) * gain_P_nW).clip(0, 2**32 - 1).astype(np.uint32)
    return power


def mem_out_power_v2(data: IVTrace | np.ndarray, cal: CalibrationSeries) -> np.ndarray:
    len_add = len(data)
    power = (
        (
            cal.voltage.raw_to_si(data.ds_voltage[:len_add]).astype(np.float32)
            * cal.current.raw_to_si(data.ds_current[:len_add]).astype(np.float32)
            / gain
        )
        .clip(0, 2**32 - 1)
        .astype(np.uint32)
    )
    return power

def mem_out_power_v3(data: IVTrace | np.ndarray, cal: CalibrationSeries) -> np.ndarray:
    len_add = len(data)
    power = (
        (
            cal.voltage.raw_to_si(data.ds_voltage[:len_add])
            * cal.current.raw_to_si(data.ds_current[:len_add])
            / gain
        )
        .clip(0, 2**32 - 1)
        .astype(np.uint32)
    )
    return power

def mem_out_power_reduce_v1(data: IVTrace | np.ndarray, reduction_factor: int) -> np.ndarray:
    len_add = len(data)
    len_red = len_add // reduction_factor
    len_add = len_red * reduction_factor
    V_ = data.ds_voltage[:len_add].clip(0, 2 ** 18 - 1).astype(np.int64) + offset_V_raw
    C_ = data.ds_current[:len_add].clip(0, 2 ** 18 - 1).astype(np.int64) + offset_C_raw
    power = ((V_ * C_) * gain_P_nW).clip(0, 2**32 - 1).astype(np.uint32)
    power = power.reshape(len_red, reduction_factor).mean(axis=1, dtype=np.uint64).astype(np.uint32)
    return power


def mem_out_power_reduce_v2(data: IVTrace | np.ndarray, reduction_factor: int) -> np.ndarray:
    len_add = len(data)
    len_red = len_add // reduction_factor
    len_add = len_red * reduction_factor
    V_ = data.ds_voltage[:len_add].clip(0, 2 ** 18 - 1).astype(np.int64) + offset_V_raw
    C_ = data.ds_current[:len_add].clip(0, 2 ** 18 - 1).astype(np.int64) + offset_C_raw
    power = (
        ((V_ * C_) * gain_P_nW)
        .reshape(len_red, reduction_factor)
        .mean(axis=1, dtype=np.int64)
        .clip(0, 2**32 - 1)
        .astype(np.uint32)
    )
    return power


def mem_out_power_reduce_v3(
    data: IVTrace | np.ndarray, reduction_factor: int, cal: CalibrationSeries
) -> np.ndarray:
    len_add = len(data)
    len_red = len_add // reduction_factor
    len_add = len_red * reduction_factor
    power = (
        (
            cal.voltage.raw_to_si(data.ds_voltage[:len_add]).astype(np.float32)
            * cal.current.raw_to_si(data.ds_current[:len_add]).astype(np.float32)
            / gain
        )
        .reshape(len_red, reduction_factor)
        .mean(axis=1, dtype=np.float32)
        .clip(0, 2**32 - 1)
        .astype(np.uint32)
    )
    return power


def mem_out_power_reduce_v4(
    data: IVTrace | np.ndarray, reduction_factor: int, cal: CalibrationSeries
) -> np.ndarray:
    len_add = len(data)
    len_red = len_add // reduction_factor
    len_add = len_red * reduction_factor
    power = (
        (
            cal.voltage.raw_to_si(data.ds_voltage)
            * cal.current.raw_to_si(data.ds_current)
            / gain
        )
        .reshape(len_red, reduction_factor)
        .mean(axis=1)
        .clip(0, 2**32 - 1)
        .astype(np.uint32)
    )
    return power

if __name__ == "__main__":
    set_verbosity()

    rng = np.random.default_rng()
    iv_trace = IVTrace(
        voltage=rng.integers(low=0, high=2**18, size=100_000, dtype=np.uint32),
        current=rng.integers(low=0, high=2**18, size=100_000, dtype=np.uint32),
    )

    repetitions = 1000
    for routine_under_test in [
        # "mem_out_iv_reduce_v1(iv_trace, 1)", -> 100x slower than (,2)-version
        "mem_out_iv_reduce_v1(iv_trace, 2)",
        "mem_out_iv_reduce_v1(iv_trace, 10)",
        "mem_out_iv_reduce_v1(iv_trace, 100)",
        "mem_out_power_v1(iv_trace)",
        "mem_out_power_v2(iv_trace, cal_data)",
        "mem_out_power_v3(iv_trace, cal_data)",
        "mem_out_power_reduce_v1(iv_trace, 2)",
        "mem_out_power_reduce_v1(iv_trace, 10)",
        "mem_out_power_reduce_v1(iv_trace, 100)",
        "mem_out_power_reduce_v2(iv_trace, 2)",
        "mem_out_power_reduce_v2(iv_trace, 10)",
        "mem_out_power_reduce_v2(iv_trace, 100)",
        "mem_out_power_reduce_v3(iv_trace, 2, cal_data)",
        "mem_out_power_reduce_v3(iv_trace, 10, cal_data)",
        "mem_out_power_reduce_v3(iv_trace, 100, cal_data)",
        "mem_out_power_reduce_v4(iv_trace, 2, cal_data)",
        "mem_out_power_reduce_v4(iv_trace, 10, cal_data)",
        "mem_out_power_reduce_v4(iv_trace, 100, cal_data)",
    ]:
        time.sleep(1)
        time_total = timeit(
            routine_under_test,
            globals=globals(),
            number=repetitions,
        )
        log.info("\t%s = %.3f s for %d reps", routine_under_test, time_total, repetitions)
