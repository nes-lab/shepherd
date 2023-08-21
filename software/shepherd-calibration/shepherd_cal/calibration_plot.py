from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from shepherd_core import CalibrationCape
from shepherd_core.data_models.base.cal_measurement import CalMeasurementCape

from .logger import logger


def plot_calibration(
    measurements: CalMeasurementCape,
    calibration: CalibrationCape,
    file_name: Path,
) -> None:
    for component in ["harvester", "emulator"]:
        msr_component = measurements[component]
        for channel in msr_component.keys():
            try:
                sample_points = msr_component[channel]
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
            plt.savefig(Path(file_name).stem + f".plot_{component}_{channel}.png")
            plt.close(fig)
            plt.clf()
