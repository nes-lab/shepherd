"""

This will try to stress the shepherd-pipeline and hopefully verify patches for uncovered issues.

"""

import time
from pathlib import Path

import numpy as np
from shepherd_core import Compression
from shepherd_core import Reader
from shepherd_core.data_models import EnergyDType
from shepherd_core.data_models import GpioTracing
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import ProgrammingTask
from shepherd_core.data_models.testbed import ProgrammerProtocol
from shepherd_core.data_models.testbed import TargetPort
from shepherd_core.hrv_format.writer import Writer as HrvWriter
from shepherd_core.logger import log
from shepherd_sheep.shepherd_run_functions import run_emulator
from shepherd_sheep.shepherd_run_functions import run_programmer

path_storage = Path("/var/shepherd/experiments")
path_firmware = Path(__file__).parent / "firmwares"

log.info(
    "| %s | CPU_min [%%] | CPU_max [%%] | CPU_mean [%%] | File [MiB/s] | Note |", "Type".ljust(34)
)
log.info("|------------------------------------|---------|---------|----------|-------|------|")


def calculate_stats(file: Path, title: str) -> None:
    with Reader(file, verbose=False) as reader:
        if "power" in reader.h5file and len(reader.h5file["power"]["time"]) > 1:
            t_start = reader.h5file["power"]["time"][0]
            t_end = reader.h5file["power"]["time"][-1]
        elif "data" in reader.h5file and len(reader.h5file["data"]["time"]) > 1:
            t_start = reader.h5file["data"]["time"][0]
            t_end = reader.h5file["data"]["time"][-1]
        else:
            _len = len(reader.h5file["sys_util"]["time"])
            t_end = reader.h5file["sys_util"]["time"][-min(5, _len)]
            t_start = reader.h5file["sys_util"]["time"][-min(65, _len)]
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
            notes.append("had errors")
        if reader.runtime_s < 60:
            notes.append("incomplete")
        if cpu_mean > 90:
            notes.append("high load")
    log.info(
        "| %s | %d | %d | %.1f | %.3f | %s |",
        title.ljust(34),
        cpu_min,
        cpu_max,
        cpu_mean,
        datarate,
        ", ".join(notes),
    )


def generate_harvest_file(
    *,
    random: bool = True,
) -> Path:
    random_str = "random" if random else "static"
    path = path_storage / f"hrv_synth_{random_str}.hrv5"
    duration = 60
    if not path.exists():
        rng = np.random.default_rng()
        samples_per_1s = 100_000
        with HrvWriter(
            path,
            datatype=EnergyDType.ivsample,
            verbose=False,
            force_overwrite=True,
        ) as sw:
            for _ in range(duration):
                if random:
                    v_ = rng.uniform(low=1.0, high=3.0, size=samples_per_1s)
                    i_ = rng.uniform(low=0.001, high=0.05, size=samples_per_1s)
                else:
                    v_ = np.linspace(3.30, 3.30, samples_per_1s)
                    i_ = np.linspace(100e-6, 2000e-6, samples_per_1s)
                sw.append_iv_data_si(voltage=v_, current=i_)
            sw.h5file.flush()
    return path


def bench_emu_stresstest() -> None:
    _rate = 1_000_000  # ~ 500 kSPS,
    title = "EMU Stresstest "
    path_output = path_storage / "emu_stresstest.h5"
    if not path_output.exists():
        path_input = path_firmware / f"build_{_rate}.hex"
        if not path_input.exists():
            log.warning("Firmware not found - will skip")
            return
        cfg = ProgrammingTask(
            firmware_file=path_input,
            mcu_type="nrf52",
            protocol=ProgrammerProtocol.SWD,
        )
        run_programmer(cfg)
        path_input = generate_harvest_file(random=False)
        time_start = int(time.time() + 30)
        cfg = EmulationTask(
            input_path=path_input,
            output_path=path_output,
            duration=240,
            use_cal_default=True,
            time_start=time_start,
            virtual_source=VirtualSourceConfig(name="neutral"),
            uart_logging=None,
            gpio_tracing=GpioTracing(),
            io_port=TargetPort.A,
            pwr_port=TargetPort.A,
            enable_io=True,
            output_compression=Compression.lzf,
        )
        log.info(title)
        time.sleep(5)
        run_emulator(cfg)
    calculate_stats(path_output, title)


if __name__ == "__main__":
    bench_emu_stresstest()
