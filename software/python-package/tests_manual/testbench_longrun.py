from pathlib import Path

from shepherd import logger
from shepherd import run_emulator
from shepherd import run_harvester

# run with
# sudo python3 /opt/shepherd/software/python-package/tests_manual/testbench_longrun.py

if __name__ == "__main__":
    duration = 600 * 60
    benchmark_path = Path("/var/shepherd/recordings")
    file_rec = benchmark_path / "benchmark_rec.h5"
    file_emu1 = benchmark_path / "benchmark_emu1.h5"
    file_emu2 = benchmark_path / "benchmark_emu2.h5"

    if not file_rec.exists():
        logger.info("Start harvesting")
        run_harvester(
            output_path=file_rec,
            duration=duration,
            force_overwrite=True,
            use_cal_default=True,
        )

    logger.info("Starting Emulation1, only logging of SysUtil-Stats")
    run_emulator(
        input_path=file_rec,
        output_path=file_emu1,
        duration=duration,
        force_overwrite=True,
        virtsource="BQ25570s",
        skip_log_gpio=True,
        skip_log_current=True,
        skip_log_voltage=True,
    )

    logger.info("Starting Emulation2, ")
    run_emulator(
        input_path=file_rec,
        output_path=file_emu2,
        duration=duration,
        force_overwrite=True,
        virtsource="BQ25570s",
    )
