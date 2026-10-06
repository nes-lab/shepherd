"""

This will run through most common config-modes and record CPU-Util

Variations:
- emulation & harvester
- IV recording & power_only
- compressions from none to gzip6
- samplerate-reduction from 1x to 100_000x
- prep-time 15, 20, 25, 30 s

Modus Operandi:
- vary 1 or 2 variables and keep the rest default or
- in case of emulation worst case (if possible)
- run 60 seconds and look at CPU-Util

-> see results-markdown-file

"""

import sys
import time
from pathlib import Path

import numpy as np
from shepherd_core import Compression
from shepherd_core import Reader
from shepherd_core.data_models import EnergyDType
from shepherd_core.data_models import PowerTracing
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_core.logger import log
from shepherd_core.writer import Writer
from shepherd_sheep.shepherd_run_functions import run_emulator
from shepherd_sheep.shepherd_run_functions import run_harvester

path_storage = Path("/var/shepherd/recordings")
skip_hrv = False

log.info("| %s | %s | %s | %s | %s |", "type".ljust(34), "cpu_min", "cpu_max", "cpu_mean", "note")
log.info("|------------------------------------|---------|---------|----------|------|")


def calculate_stats(file: Path, title: str) -> None:
    with Reader(file, verbose=False) as reader:
        if "power" in reader.h5file and reader.h5file["power"]["time"].shape[0] > 1:
            t_start = reader.h5file["power"]["time"][0]
            t_end = reader.h5file["power"]["time"][-1]
        else:
            t_start = reader.h5file["data"]["time"][0]
            t_end = reader.h5file["data"]["time"][-1]
        ds_time = reader.h5file["sys_util"]["time"]
        ds_cpu = reader.h5file["sys_util"]["cpu"]
        ds_filter = ds_time[:] >= t_start  # / ds_time.attrs["gain"]
        ds_filter &= ds_time[:] <= t_end  # / ds_time.attrs["gain"]
        cpu_selection = ds_cpu[ds_filter]
        cpu_mean = np.mean(cpu_selection)
        cpu_max = np.max(cpu_selection)
        cpu_min = np.min(cpu_selection)
    log.info("| %s | %d | %d | %.1f | - |", title.ljust(34), cpu_min, cpu_max, cpu_mean)


def bench_hrv_sweep_starttime() -> None:
    for _offset in range(10, 30, 5):
        title = f"HRV t_offset={_offset}"
        path_output = path_storage / f"hrv_toffset{_offset}.h5"
        if not path_output.exists():
            time_start = int(time.time() + _offset)
            cfg = HarvestTask(
                output_path=path_output,
                time_start=time_start,
                duration=60,
                use_cal_default=True,
            )
            log.info(title)
            run_harvester(cfg)
        calculate_stats(path_output, title)


def bench_hrv_sweep_samplerate_poweronly() -> None:
    for _power_only in [True, False]:
        for _samplerate in [10, 100, 1_000, 100_000]:
            _pwr_add = "power" if _power_only else "iv"
            title = f"HRV {_pwr_add} & samplerate={_samplerate}"
            path_output = path_storage / f"hrv_{_pwr_add}_samplerate{_samplerate}.h5"
            if not path_output.exists():
                time_start = int(time.time() + 20)
                power_tracer = PowerTracing(only_power=_power_only, samplerate=_samplerate)
                cfg = HarvestTask(
                    output_path=path_output,
                    time_start=time_start,
                    duration=60,
                    use_cal_default=True,
                    power_tracing=power_tracer,
                )
                log.info(title)
                run_harvester(cfg)
            calculate_stats(path_output, title)


def bench_hrv_sweep_compression() -> None:
    for _compression in [Compression.null, Compression.lzf, Compression.gzip1, Compression.gzip6]:
        title = f"HRV compression={_compression.value}"
        path_output = path_storage / f"hrv_compression{_compression.value}.h5"
        if not path_output.exists():
            time_start = int(time.time() + 20)
            cfg = HarvestTask(
                output_path=path_output,
                time_start=time_start,
                duration=60,
                use_cal_default=True,
                output_compression=_compression,
            )
            log.info(title)
            run_harvester(cfg)
        calculate_stats(path_output, title)


def generate_harvest_file(
    compression: Compression,
    *,
    random: bool = True,
) -> Path:
    rand_str = "random" if random else "static"
    path = path_storage / f"hrv_synth_{compression.value}_{rand_str}.h5"
    duration = 60
    if not path.exists():
        rng = np.random.default_rng()
        samples_per_1s = Writer.CHUNK_SAMPLES_N * 10
        with Writer(
            path,
            mode="harvester",
            datatype=EnergyDType.ivsample,
            verbose=False,
            force_overwrite=True,
            compression=compression,
        ) as sw:
            sw.store_hostname("Hrv")
            for _iter in range(duration):
                if random:
                    v_ = rng.uniform(low=1.0, high=3.0, size=samples_per_1s)
                    i_ = rng.uniform(low=0.001, high=0.05, size=samples_per_1s)
                else:
                    v_ = np.linspace(3.30, 3.30, samples_per_1s)
                    i_ = np.linspace(100e-6, 2000e-6, samples_per_1s)
                sw.append_iv_data_si(timestamp=_iter, voltage=v_, current=i_)
            sw.h5file.flush()
    return path


def bench_emu_sweep_starttime() -> None:
    path_input = generate_harvest_file(Compression.gzip6, random=True)  # Worst Case!
    for _offset in range(15, 35, 5):
        title = f"EMU t_offset={_offset}"
        path_output = path_storage / f"emu_toffset{_offset}.h5"
        if not path_output.exists():
            time_start = int(time.time() + _offset)
            cfg = EmulationTask(
                input_path=path_input,
                output_path=path_output,
                duration=60,
                use_cal_default=True,
                time_start=time_start,
                virtual_source=VirtualSourceConfig(name="neutral"),
                uart_logging=None,
                gpio_tracing=None,
            )
            log.info(title)
            run_emulator(cfg)
        calculate_stats(path_output, title)


def bench_emu_sweep_samplerate_poweronly() -> None:
    path_input = generate_harvest_file(Compression.gzip6, random=True)  # Worst Case!
    for _power_only in [True, False]:
        for _samplerate in [10, 100, 1_000, 100_000]:
            _pwr_add = "power" if _power_only else "iv"
            title = f"EMU {_pwr_add} & samplerate={_samplerate}"
            path_output = path_storage / f"emu_{_pwr_add}_samplerate{_samplerate}.h5"
            if not path_output.exists():
                time_start = int(time.time() + 25)
                power_tracer = PowerTracing(only_power=_power_only, samplerate=_samplerate)
                cfg = EmulationTask(
                    input_path=path_input,
                    output_path=path_output,
                    duration=60,
                    use_cal_default=True,
                    time_start=time_start,
                    virtual_source=VirtualSourceConfig(name="neutral"),
                    uart_logging=None,
                    gpio_tracing=None,
                    power_tracing=power_tracer,
                )
                log.info(title)
                run_emulator(cfg)
            calculate_stats(path_output, title)


def bench_emu_sweep_output_compression() -> None:
    path_input = generate_harvest_file(Compression.gzip6, random=True)  # Worst Case!
    for _compression in [Compression.null, Compression.lzf, Compression.gzip1, Compression.gzip6]:
        title = f"EMU output-compression={_compression.value}"
        path_output = path_storage / f"emu_output_compression{_compression.value}.h5"
        if not path_output.exists():
            time_start = int(time.time() + 25)
            cfg = EmulationTask(
                input_path=path_input,
                output_path=path_output,
                duration=60,
                use_cal_default=True,
                time_start=time_start,
                virtual_source=VirtualSourceConfig(name="neutral"),
                uart_logging=None,
                gpio_tracing=None,
                output_compression=_compression,
            )
            log.info(title)
            run_emulator(cfg)
        calculate_stats(path_output, title)


def bench_emu_sweep_input_compression() -> None:
    for _compression in [Compression.null, Compression.lzf, Compression.gzip1, Compression.gzip6]:
        title = f"EMU input-compression={_compression.value}"
        path_output = path_storage / f"emu_input_compression{_compression.value}.h5"
        if not path_output.exists():
            path_input = generate_harvest_file(_compression, random=True)
            time_start = int(time.time() + 25)
            cfg = EmulationTask(
                input_path=path_input,
                output_path=path_output,
                duration=60,
                use_cal_default=True,
                time_start=time_start,
                virtual_source=VirtualSourceConfig(name="neutral"),
                uart_logging=None,
                gpio_tracing=None,
            )
            log.info(title)
            run_emulator(cfg)
        calculate_stats(path_output, title)


if __name__ == "__main__":
    bench_emu_sweep_starttime()
    bench_emu_sweep_samplerate_poweronly()
    bench_emu_sweep_output_compression()
    bench_emu_sweep_input_compression()

    if skip_hrv:
        sys.exit(0)

    bench_hrv_sweep_starttime()
    bench_hrv_sweep_samplerate_poweronly()
    bench_hrv_sweep_compression()
