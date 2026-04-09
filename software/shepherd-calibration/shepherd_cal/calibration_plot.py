from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from shepherd_core.data_models.base.cal_measurement import CalMeasurementCape
from shepherd_core.data_models.base.calibration import CalibrationCape
from shepherd_core.data_models.base.calibration import CalibrationEmulator
from shepherd_core.data_models.base.calibration import CalibrationHarvester

from .logger import log


def plot_calibration(
    measurements: CalMeasurementCape,
    calibration: CalibrationCape,
    file_name: Path,
) -> None:
    for component in ["harvester", "emulator"]:
        msr_component: CalibrationHarvester | CalibrationEmulator = measurements[component]
        if msr_component is None:
            log.info(
                "NOTE: data for component '%s' not found - will skip plot",
                component,
            )
            continue
        for channel in msr_component.keys():  # noqa: SIM118
            # dict-access works on basemodel
            path_plot = Path(file_name).with_suffix(f".plot_{component}_{channel}.png")
            if path_plot.exists():
                log.info(
                    "NOTE: plot '%s' already exists - will skip",
                    path_plot,
                )
                continue
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
            except LookupError:  # KeyError & IndexError
                log.info(
                    "NOTE: data for channel '%s' was not found - will skip plot",
                    channel,
                )
                continue
            except ValueError as e:
                log.info(
                    "NOTE: data for channel '%s' was faulty - will skip plot",
                    channel,
                    exc_info=e,
                )
                continue

            fig, ax = plt.subplots()
            ax.plot(xl, yl, ":", linewidth=2, color="green")
            ax.scatter(xp, yp, marker="*", color="k")
            ax.set_xlabel(r"raw value", fontsize=10)
            ax.set_ylabel(r"SI-Unit", fontsize=10)
            ax.set_title(f"Calibration-Check for {component} - {channel}")
            ax.grid(visible=True)
            fig.set_figwidth(11)
            fig.set_figheight(10)
            fig.tight_layout()
            plt.savefig(path_plot)
            plt.close(fig)
            plt.clf()
