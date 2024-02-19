from pathlib import Path

from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask
from shepherd_sheep import log
from shepherd_sheep import run_emulator
from shepherd_sheep import run_harvester

# run on observer with
# sudo python3 /opt/shepherd/software/python-package/tests_manual/testbench_longrun.py

if __name__ == "__main__":
    duration = 10 * 60 * 60  # s
    benchmark_path = Path("/var/shepherd/recordings")
    file_rec = benchmark_path / "benchmark_rec.h5"
    file_emu1 = benchmark_path / "benchmark_emu1.h5"
    file_emu2 = benchmark_path / "benchmark_emu2.h5"

    if not file_rec.exists():
        log.info("Start harvesting")
        hrv = HarvestTask(
            output_path=file_rec,
            duration=duration,
            force_overwrite=True,
            use_cal_default=True,
        )
        run_harvester(hrv)

    log.info("Starting Emulation1, only logging of SysUtil-Stats")
    emu1 = EmulationTask(
        input_path=file_rec,
        output_path=file_emu1,
        duration=duration,
        force_overwrite=True,
        virtual_source=VirtualSourceConfig(name="BQ25570s"),
        power_tracing=None,
        gpio_tracing=None,
        verbose=3,
    )
    run_emulator(emu1)

    log.info("Starting Emulation2, ")
    emu2 = EmulationTask(
        input_path=file_rec,
        output_path=file_emu2,
        duration=duration,
        force_overwrite=True,
        virtual_source=VirtualSourceConfig(name="BQ25570s"),
        verbose=3,
    )
    run_emulator(emu2)
