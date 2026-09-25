"""Worst Case (RNG) test of the embedded recoders

   This will benchmark sheep-routines:
   - iv-writer      (100 kHz, isochronous, 2 datasets)
   - PowerRecorder  (smaller alternative to IV, 1 dataset)
   - GpioRecorder   (high dynamic, event driven, 16 bit mask)
   - PruRecorder    (rare exec, every 0.1s, isochronous, 4 datasets

result 2026-09-21 - baseline
    samples_n = 1000000 n, Compression.null
        IV, t = 1.410 s, out = 15.294 MiB
        PW, t = 2.294 s, out = 11.495 MiB
        GP, t = 1.182 s, out = 9.584 MiB
        UT, t = 7.549 s, out = 14.178 MiB
    samples_n = 1000000 n, Compression.lzf
        IV, t = 3.920 s, out = 12.580 MiB
        PW, t = 2.905 s, out = 5.015 MiB
        GP, t = 2.550 s, out = 6.726 MiB
        UT, t = 15.301 s, out = 11.671 MiB
    samples_n = 1000000 n, Compression.gzip1
        IV, t = 4.328 s, out = 9.989 MiB
        PW, t = 3.175 s, out = 2.665 MiB
        GP, t = 2.709 s, out = 4.530 MiB
        UT, t = 25.939 s, out = 9.790 MiB

result 2026-09-21 - shuffle, chunk-optimized timestamps
    samples_n = 1000000 n, Compression.null
        IV, t = 1.440 s, out = 15.294 MiB
        PW, t = 2.733 s, out = 11.467 MiB
        GP, t = 1.165 s, out = 9.558 MiB
        UT, t = 8.288 s, out = 14.178 MiB
    samples_n = 1000000 n, Compression.lzf
        IV, t = 3.112 s, out = 8.123 MiB
        PW, t = 1.969 s, out = 0.525 MiB
        GP, t = 1.935 s, out = 3.850 MiB
        UT, t = 14.897 s, out = 8.439 MiB
    samples_n = 1000000 n, Compression.gzip1
        IV, t = 3.319 s, out = 7.496 MiB        -> 25 % faster
        PW, t = 2.202 s, out = 0.295 MiB        -> 50 % faster
        GP, t = 2.296 s, out = 3.622 MiB        -> 18 % faster
        UT, t = 24.917 s, out = 8.317 MiB
    samples_n = 1000000 n, Compression.gzip6
        IV, t = 3.695 s, out = 7.366 MiB
        PW, t = 2.474 s, out = 0.186 MiB
        GP, t = 2.690 s, out = 3.588 MiB
        UT, t = 27.221 s, out = 8.317 MiB

result 2026-09-22 - kernel 6.12.109 & 6.18.52 (kMod not running)
    samples_n = 1000000 n, Compression.null
        IV, t = 1.236 s, out = 15.294 MiB
        PW, t = 2.091 s, out = 11.467 MiB
        GP, t = 1.029 s, out = 9.558 MiB
        UT, t = 6.518 s, out = 14.178 MiB
    samples_n = 1000000 n, Compression.lzf
        IV, t = 2.829 s, out = 8.123 MiB
        PW, t = 1.803 s, out = 0.525 MiB
        GP, t = 1.770 s, out = 3.851 MiB
        UT, t = 12.340 s, out = 8.452 MiB
    samples_n = 1000000 n, Compression.gzip1
        IV, t = 3.020 s, out = 7.496 MiB
        PW, t = 2.037 s, out = 0.295 MiB
        GP, t = 2.099 s, out = 3.621 MiB
        UT, t = 20.706 s, out = 8.318 MiB
    samples_n = 1000000 n, Compression.gzip6
        IV, t = 3.417 s, out = 7.366 MiB
        PW, t = 2.275 s, out = 0.186 MiB
        GP, t = 2.485 s, out = 3.588 MiB
        UT, t = 22.982 s, out = 8.318 MiB
"""

import time
from pathlib import Path
from timeit import timeit

import numpy as np
from shepherd_core import Compression
from shepherd_core.data_models import EnergyDType
from shepherd_core.data_models.base.calibration import CalibrationSeries
from shepherd_core.logger import log
from shepherd_sheep.h5_writer import Writer
from shepherd_sheep.shared_mem_gpio_output import GPIOTrace
from shepherd_sheep.shared_mem_iv_input import IVTrace
from shepherd_sheep.shared_mem_util_output import UtilTrace


def generate_iv(sample_count: int) -> list[IVTrace]:
    rng = np.random.default_rng()
    samples_per_trace = Writer.CHUNK_SAMPLES_N * 10  # 1 s
    samples = []
    cal = CalibrationSeries()
    time_vector = np.arange(0, 10**9, 10**9 // samples_per_trace)
    for _iter in range(sample_count // samples_per_trace):
        trace = IVTrace(
            voltage=cal.voltage.si_to_raw(rng.uniform(low=1.0, high=3.0, size=samples_per_trace)),
            current=cal.current.si_to_raw(
                rng.uniform(low=0.001, high=0.05, size=samples_per_trace)
            ),
            timestamp_ns=_iter + time_vector,
        )
        samples.append(trace)
    return samples


def generate_gpio(sample_count: int) -> list[GPIOTrace]:
    rng = np.random.default_rng()
    samples_per_trace = 10**6
    samples = []
    time_vector = np.arange(0, 10**9, 10**9 // samples_per_trace)
    for _iter in range(sample_count // samples_per_trace):
        trace = GPIOTrace(
            timestamps_ns=_iter
            + time_vector
            + rng.uniform(low=0, high=10**9 // samples_per_trace - 1, size=samples_per_trace),
            bitmasks=rng.uniform(low=0, high=2**16 - 1, size=samples_per_trace),
        )
        samples.append(trace)
    return samples


def generate_util(sample_count: int) -> list[UtilTrace]:
    rng = np.random.default_rng()
    samples_per_trace = 10**6
    samples = []
    time_vector = np.arange(0, 10**9, 10**9 // samples_per_trace)
    for _iter in range(sample_count // samples_per_trace):
        trace = UtilTrace(
            timestamps_ns=_iter + time_vector,
            pru0_tsample_mean=rng.uniform(low=0, high=10_000, size=samples_per_trace),
            pru0_tsample_max=rng.uniform(low=0, high=10_000, size=samples_per_trace),
            pru1_tsample_max=rng.uniform(low=0, high=10_000, size=samples_per_trace),
            sample_count=rng.uniform(low=9_000, high=10_000, size=samples_per_trace),
        )
        samples.append(trace)
    return samples


def iv_to_file(path: Path, data: list[IVTrace], compression: Compression) -> None:
    with Writer(
        path,
        mode="emulator",
        datatype=EnergyDType.ivsample,
        verbose=False,
        force_overwrite=True,
        compression=compression,
    ) as sw:
        sw.store_hostname("Emu")
        for _date in data:
            sw.write_iv_buffer(_date)
        sw.h5file.flush()


def pw_to_file(path: Path, data: list[IVTrace], compression: Compression) -> None:
    with Writer(
        path,
        mode="emulator",
        datatype=EnergyDType.ivsample,
        verbose=False,
        force_overwrite=True,
        compression=compression,
        only_power=True,
    ) as sw:
        sw.store_hostname("Emu")
        for _date in data:
            sw.write_iv_buffer(_date)
        sw.h5file.flush()


def gp_to_file(path: Path, data: list[GPIOTrace], compression: Compression) -> None:
    with Writer(
        path,
        mode="emulator",
        datatype=EnergyDType.ivsample,
        verbose=False,
        force_overwrite=True,
        compression=compression,
    ) as sw:
        sw.store_hostname("Emu")
        for _date in data:
            sw.write_gpio_buffer(_date)
        sw.h5file.flush()


def ut_to_file(path: Path, data: list[UtilTrace], compression: Compression) -> None:
    with Writer(
        path,
        mode="emulator",
        datatype=EnergyDType.ivsample,
        verbose=False,
        force_overwrite=True,
        compression=compression,
    ) as sw:
        sw.store_hostname("Emu")
        for _date in data:
            sw.write_util_buffer(_date)
        sw.h5file.flush()


if __name__ == "__main__":
    sample_count = 1_000_000
    compressions = [Compression.null, Compression.lzf, Compression.gzip1, Compression.gzip6]
    path_iv = Path(__file__).parent / "benchIV.h5"
    path_pw = Path(__file__).parent / "benchPW.h5"
    path_gp = Path(__file__).parent / "benchGP.h5"
    path_ut = Path(__file__).parent / "benchUT.h5"

    for compression in compressions:
        traces = generate_iv(sample_count)  # 10 s
        time.sleep(1)
        tiv = timeit(
            "iv_to_file(path_iv, traces, compression)",
            globals=globals(),
            number=1,
        )

        traces = generate_iv(sample_count)
        time.sleep(1)
        tpw = timeit(
            "pw_to_file(path_pw, traces, compression)",
            globals=globals(),
            number=1,
        )

        traces = generate_gpio(sample_count)
        time.sleep(1)
        tgp = timeit(
            "gp_to_file(path_gp, traces, compression)",
            globals=globals(),
            number=1,
        )

        traces = generate_util(sample_count)
        time.sleep(1)
        tut = timeit(
            "ut_to_file(path_ut, traces, compression)",
            globals=globals(),
            number=1,
        )
        traces = 0

        log.info("samples_n = %d n, %s", sample_count, str(compression))
        log.info(
            "\tIV, t = %.3f s, out = %.3f MiB",
            tiv,
            path_iv.stat().st_size / 2**20,
        )
        log.info(
            "\tPW, t = %.3f s, out = %.3f MiB",
            tpw,
            path_pw.stat().st_size / 2**20,
        )
        log.info(
            "\tGP, t = %.3f s, out = %.3f MiB",
            tgp,
            path_gp.stat().st_size / 2**20,
        )
        log.info(
            "\tUT, t = %.3f s, out = %.3f MiB",
            tut,
            path_ut.stat().st_size / 2**20,
        )

        time.sleep(1)
        path_iv.unlink()
        path_pw.unlink()
        path_gp.unlink()
        path_ut.unlink()
