from pathlib import Path

from shepherd import record, emulate

# run with
# sudo python3 /opt/shepherd/software/python-package/shepherd/testbench_longrun.py

if __name__ == "__main__":
    duration = 600 * 60
    benchmark_path = Path("/var/shepherd/recordings")
    file_rec = benchmark_path / "benchmark_rec.h5"
    file_emu1 = benchmark_path / "benchmark_emu1.h5"
    file_emu2 = benchmark_path / "benchmark_emu2.h5"

    if not file_rec.exists():
        print("Starting Harvesting")
        record(output_path=file_rec,
               duration=duration,
               force_overwrite=True,
               use_cal_default=True,)

    print("Starting Emulation1, only logging of SysUtil-Stats")
    emulate(input_path=file_rec,
            output_path=file_emu1,
            duration=duration,
            force_overwrite=True,
            virtsource="BQ25570s",
            skip_log_gpio=True,
            skip_log_current=True,
            skip_log_voltage=True,
            )

    print("Starting Emulation2, ")
    emulate(input_path=file_rec,
            output_path=file_emu2,
            duration=duration,
            force_overwrite=True,
            virtsource="BQ25570s", )
