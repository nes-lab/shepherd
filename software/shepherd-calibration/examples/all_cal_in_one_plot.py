from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from shepherd_core import CalibrationEmulator
from shepherd_core.data_models.base.cal_measurement import CalMeasurementCape
from shepherd_core.logger import log

# Config
path_here = Path(__file__).parent
path_measurements = path_here / "data"
analyze_zero_crossing: bool = True  # -> zoom in

meas_files = path_measurements.glob("*.measurement.yaml")
# -> cal-data is automatically derived from this

fig, ax = plt.subplots()

for meas_file in meas_files:
    try:
        cms = CalMeasurementCape.from_file(meas_file)
    except ValueError:
        log.warning("Could not load provided %s -> will skip", meas_file)
        continue

    try:
        cal = cms.to_cal()
    except ValueError:
        log.warning("Could not generate Cal from %s -> will skip", meas_file)
        continue

    for component in ["emulator"]:
        csm_component: CalibrationEmulator = cms[component]
        if csm_component is None:
            log.info(
                "NOTE: data for component '%s' not found - will skip plot",
                component,
            )
            continue
        for channel in ["adc_C_A", "adc_C_B"]:
            try:
                sample_points = csm_component[channel]
                xp = np.empty(len(sample_points))
                yp = np.empty(len(sample_points))
                for i, point in enumerate(sample_points):
                    xp[i] = point["shepherd_raw"]
                    yp[i] = point["reference_si"]
                gain = cal[component][channel]["gain"]
                offset = cal[component][channel]["offset"]
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
            label = meas_file.stem.split(".")[0][-12:] + f"_{channel}"
            ax.plot(xl, yl, ":", linewidth=2, label=label)
            ax.scatter(xp, yp, marker="*")

if analyze_zero_crossing:
    ax.set_xlim([400, 1000])
    ax.set_ylim([0, 110e-6])

ax.set_xlabel(r"raw value", fontsize=10)
ax.set_ylabel(r"SI-Unit", fontsize=10)
ax.grid(visible=True)

fig.set_figwidth(11)
fig.set_figheight(10)
fig.tight_layout()
fig.legend(loc="upper left")

plt.savefig(path_here / f"all_in_one_{path_measurements.name}.png")
plt.close(fig)
plt.clf()
