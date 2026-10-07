"""

This will run through most common config-modes and record CPU-Util

Variations:
- emulation & harvester
- IV recording & power_only
- compressions from none to gzip6
- samplerate-reduction from 1x to 100_000x
- prep-time 15, 20, 25, 30 s
- pre-scaling, vs native harvest-files as input for EMU
- random vs static input as input for EMU
- try uart & gpio-capture with the target uart-firmwares

TODO:
- try different vsrouces,
- try intermediate voltage
- try prepared .hrv-files

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
from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models import PowerTracing
from shepherd_core.data_models import UartLogging
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.base.calibration import CalibrationPair
from shepherd_core.data_models.base.calibration import CalibrationSeries
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.testbed import ProgrammerProtocol
from shepherd_core.logger import log
from shepherd_core.writer import Writer
from shepherd_sheep.shepherd_run_functions import run_emulator
from shepherd_sheep.shepherd_run_functions import run_harvester
from shepherd_sheep.shepherd_run_functions import run_programmer

path_storage = Path("/var/shepherd/recordings")
path_firmware = Path(__file__).parent / "firmwares"
skip_hrv = False

log.info("| %s | cpu_min | cpu_max | cpu_mean | MiB/s | note |", "type".ljust(34))
log.info("|------------------------------------|---------|---------|----------|-------|------|")


def calculate_stats(file: Path, title: str) -> None:
    with Reader(file, verbose=False) as reader:
        if "power" in reader.h5file and reader.h5file["power"]["time"].shape[0] > 1:
            t_start = reader.h5file["power"]["time"][0]
            t_end = reader.h5file["power"]["time"][-1]
        elif "data" in reader.h5file and reader.h5file["data"]["time"].shape[0] > 1:
            t_start = reader.h5file["data"]["time"][0]
            t_end = reader.h5file["data"]["time"][-1]
        else:
            t_end = reader.h5file["sys_util"]["time"][-5]
            t_start = reader.h5file["sys_util"]["time"][-65]
        ds_time = reader.h5file["sys_util"]["time"]
        ds_cpu = reader.h5file["sys_util"]["cpu"]
        ds_filter = ds_time[:] >= t_start  # / ds_time.attrs["gain"]
        ds_filter &= ds_time[:] <= t_end  # / ds_time.attrs["gain"]
        cpu_selection = ds_cpu[ds_filter]
        cpu_mean = np.mean(cpu_selection)
        cpu_max = np.max(cpu_selection)
        cpu_min = np.min(cpu_selection)
        datarate = file.stat().st_size / (60 * 2**20)
        notes = []
        if not reader.is_valid() or reader.count_errors_in_log() > 0:
            notes.append("faulty")
        if reader.runtime_s < 60:
            notes.append("incomplete")
        if cpu_mean > 90:
            notes.append("overload")
    log.info(
        "| %s | %d | %d | %.1f | %.3f | %s |",
        title.ljust(34),
        cpu_min,
        cpu_max,
        cpu_mean,
        datarate,
        ", ".join(notes),
    )


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
            time.sleep(5)
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
                time.sleep(5)
                run_harvester(cfg)
            calculate_stats(path_output, title)


def bench_hrv_sweep_compression() -> None:
    for _compression in [Compression.null, Compression.lzf, Compression.gzip1]:  # gzip6
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
            time.sleep(5)
            run_harvester(cfg)
        calculate_stats(path_output, title)


def generate_harvest_file(
    compression: Compression,
    *,
    random: bool = True,
    scaled: bool = False,
) -> Path:
    random_str = "random" if random else "static"
    scaled_str = "scaled" if scaled else "native"
    path = path_storage / f"hrv_synth_{compression.value}_{random_str}_{scaled_str}.h5"
    duration = 60
    if not path.exists():
        rng = np.random.default_rng()
        samples_per_1s = Writer.CHUNK_SAMPLES_N * 10
        cal_data = (
            CalibrationSeries(
                # sheep can skip scaling if cal is ideal (applied here)
                voltage=CalibrationPair(gain=1e-6, offset=0),
                current=CalibrationPair(gain=1e-9, offset=0),
            )
            if scaled
            else None
        )
        with Writer(
            path,
            mode="harvester",
            datatype=EnergyDType.ivsample,
            verbose=False,
            force_overwrite=True,
            compression=compression,
            cal_data=cal_data,
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
    path_input = generate_harvest_file(Compression.lzf, random=True)  # Worst Case!
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
            time.sleep(5)
            run_emulator(cfg)
        calculate_stats(path_output, title)


def bench_emu_sweep_samplerate_poweronly() -> None:
    path_input = generate_harvest_file(Compression.lzf, random=True)  # Worst Case!
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
                time.sleep(5)
                run_emulator(cfg)
            calculate_stats(path_output, title)


def bench_emu_sweep_output_compression() -> None:
    path_input = generate_harvest_file(Compression.lzf, random=True)  # Worst Case!
    for _compression in [Compression.null, Compression.lzf, Compression.gzip1]:  # gzip6
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
            time.sleep(5)
            run_emulator(cfg)
        calculate_stats(path_output, title)


def bench_emu_sweep_input_compression() -> None:
    for _compression in [Compression.null, Compression.lzf, Compression.gzip1]:  # gzip6
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
            time.sleep(5)
            run_emulator(cfg)
        calculate_stats(path_output, title)


def bench_emu_sweep_input_options() -> None:
    for _scaled in [False, True]:
        for _random in [False, True]:
            _scaled_add = "scaled" if _scaled else "native"
            _random_add = "random" if _random else "static"
            title = f"EMU input-option={_scaled_add}+{_random_add}"
            path_output = path_storage / f"emu_input-option_{_scaled_add}+{_random_add}.h5"
            if not path_output.exists():
                path_input = generate_harvest_file(Compression.lzf, random=_random, scaled=_scaled)
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
                time.sleep(5)
                run_emulator(cfg)
            calculate_stats(path_output, title)


def bench_emu_sweep_datarates() -> None:
    for _rate in [
        57_600,
        115_200,
        230_400,
    ]:  # ,  460_800, 921_600, 1_000_000]:
        for _type in ["uart", "gpio"]:
            title = f"EMU {_type} datarate{_rate}"
            path_output = path_storage / f"emu_{_type}_rate_{_rate}.h5"
            if not path_output.exists():
                path_input = path_firmware / f"build_{_rate}.hex"
                if not path_input.exists():
                    log.warning("Firmware not found - will skip")
                    continue
                cfg = ProgrammingTask(
                    firmware_file=path_input,
                    mcu_type="nrf52",
                    protocol=ProgrammerProtocol.SWD,
                )
                run_programmer(cfg)
                path_input = generate_harvest_file(Compression.lzf, random=True, scaled=True)
                time_start = int(time.time() + 25)
                cfg = EmulationTask(
                    input_path=path_input,
                    output_path=path_output,
                    duration=60,
                    use_cal_default=True,
                    time_start=time_start,
                    virtual_source=VirtualSourceConfig(name="neutral"),
                    uart_logging=UartLogging(baudrate=_rate) if _type == "uart" else None,
                    gpio_tracing=GpioTracing() if _type == "gpio" else None,
                )
                log.info(title)
                time.sleep(5)
                run_emulator(cfg)
            calculate_stats(path_output, title)


def bench_emu_optimized() -> None:
    for _type in ["ivtrace", "notrace"]:
        title = f"EMU optimized {_type}"
        path_output = path_storage / f"emu_optimized_{_type}.h5"
        if not path_output.exists():
            path_input = generate_harvest_file(Compression.lzf, random=True, scaled=True)
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
                output_compression=Compression.lzf,
                power_tracing=PowerTracing() if _type == "ivtrace" else None,
            )
            log.info(title)
            time.sleep(5)
            run_emulator(cfg)
        calculate_stats(path_output, title)


if __name__ == "__main__":
    bench_emu_optimized()
    bench_emu_sweep_datarates()
    bench_emu_sweep_input_options()
    bench_emu_sweep_starttime()
    bench_emu_sweep_samplerate_poweronly()
    bench_emu_sweep_output_compression()
    bench_emu_sweep_input_compression()

    if skip_hrv:
        sys.exit(0)

    bench_hrv_sweep_starttime()
    bench_hrv_sweep_samplerate_poweronly()
    bench_hrv_sweep_compression()
