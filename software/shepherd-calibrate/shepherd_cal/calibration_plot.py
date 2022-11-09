from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .logger import logger


def plot_calibration(measurements: dict, calibration: dict, file_name: Path):
    for component in ["harvester", "emulator"]:
        for channel in ["dac_voltage_a", "dac_voltage_b", "adc_current", "adc_voltage"]:
            try:
                sample_points = measurements[component][channel]
                xp = np.empty(len(sample_points))
                yp = np.empty(len(sample_points))
                for i, point in enumerate(sample_points):
                    xp[i] = point["shepherd_raw"]
                    yp[i] = point["reference_si"]
                gain = calibration[component][channel]["gain"]
                offset = calibration[component][channel]["offset"]
                xl = [xp[0], xp[-1]]
                yl = [gain * xlp + offset for xlp in xl]
            except KeyError:
                logger.info("NOTE: data was not found - will skip plot")
                continue
            except ValueError as e:
                logger.info("NOTE: data was faulty - will skip plot", exc_info=e)
                continue

            fig, ax = plt.subplots()
            ax.plot(xl, yl, ":", linewidth=2, color="green")
            ax.scatter(xp, yp, marker="*", color="k")
            ax.set_xlabel(r"raw value", fontsize=10)
            ax.set_ylabel(r"SI-Unit", fontsize=10)
            ax.set_title(f"Calibration-Check for {component} - {channel}")
            ax.grid(True)
            fig.set_figwidth(11)
            fig.set_figheight(10)
            fig.tight_layout()
            plt.savefig(Path(file_name).stem + f"_plot_{component}_{channel}.png")
            plt.close(fig)
            plt.clf()
