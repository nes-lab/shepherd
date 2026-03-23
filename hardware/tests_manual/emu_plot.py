"""Test of possible GPIO-Plotting-Options."""

from datetime import datetime
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt
from shepherd_core.logger import log as logger
from shepherd_data import Reader

files = [
    Path(__file__).parent / "emu_tp1_3V.h5",
    Path(__file__).parent / "emu_tp2_3V.h5",
    Path(__file__).parent / "emu_tp1_hrv.h5",
    Path(__file__).parent / "emu_tp2_hrv.h5",
]
time_start = 0
time_stop = 10

plot_multi_axis = False
plot_single_axis = True
plot_live_view = False


for file in files:
    with Reader(file, verbose=False) as shpr:
        shpr.plot_to_file(time_start, time_stop, only_pwr=False)
        gpio_names = shpr.get_gpio_pin_names()
        if not isinstance(gpio_names, list):
            continue
        time_zero = shpr.get_time_start()
        if isinstance(time_zero, datetime):
            timestamp = time_zero.timestamp()
        else:
            timestamp = shpr.h5file["gpio"]["time"][0] / 1e9

        # MultiAxis
        if plot_multi_axis:
            fig, axs = plt.subplots(
                len(gpio_names), figsize=(18, 8), sharex=True, sharey=True
            )  # , layout="tight")
            for _i, gpio_name in enumerate(gpio_names):
                logger.debug("\t .. processing '%s'", gpio_name)
                wfs = shpr.get_gpio_waveforms(gpio_name)
                for gpio_name2, wf in wfs.items():
                    gpio_wf = wf.astype(float)
                    gpio_wf[:, 0] = gpio_wf[:, 0] / 1e9 - timestamp
                    # TODO: filter for time, repair first? we need one more entry on each side
                    axs[_i].step(gpio_wf[:, 0], gpio_wf[:, 1], label=gpio_name2)
                    axs[_i].set_xlabel("time [s]")
                    # axs[_i].set_ylabel("gpio_level [n]")
                    axs[_i].get_yaxis().get_major_formatter().set_useOffset(False)
                    axs[_i].get_xaxis().get_major_formatter().set_useOffset(False)
                    # axs[_i].tick_params(left=False)
                    axs[_i].set_yticks([])
            fig.legend()
            fig.suptitle("GPIO-Trace")
            file_img = file.with_suffix(".multiAxis.png")
            if file_img.exists():
                file_img.unlink()
            fig.savefig(file_img)
            plt.close()

        # SingleAxis
        if plot_single_axis:
            fig, ax = plt.subplots(figsize=(18, 8), layout="tight")
            gpio_count = len(gpio_names)
            for _i, gpio_name in enumerate(gpio_names):
                logger.debug("\t .. processing '%s'", gpio_name)
                wfs = shpr.get_gpio_waveforms(gpio_name)
                for gpio_name2, wf in wfs.items():
                    # prepare time-format
                    gpio_wf = wf.astype(float)
                    gpio_wf[:, 0] = gpio_wf[:, 0] / 1e9 - timestamp
                    # prevent empty
                    if len(gpio_wf) < 1:
                        gpio_wf = np.array([[0, 0]])
                    # filter time-slot, also add padding to fix incomplete drawing
                    idx_start = np.searchsorted(gpio_wf[:, 0], time_start, side="left")
                    idx_stop = np.searchsorted(gpio_wf[:, 0], time_stop, side="left")
                    if idx_start < 1:
                        gpio_wf = np.vstack([gpio_wf[0], gpio_wf])
                        idx_start += 1
                        idx_stop += 1
                    if idx_stop >= len(gpio_wf) - 1:
                        gpio_wf = np.vstack([gpio_wf, gpio_wf[-1]])
                    # TODO: power_good is gone on detail-plots
                    gpio_wf = gpio_wf[idx_start - 1 : idx_stop + 1]
                    gpio_wf[0, 0] = time_start
                    gpio_wf[-1, 0] = time_stop
                    # arrange waveforms on single plot
                    y_offset = 1.2 * (gpio_count - _i - 1)
                    gpio_wf[:, 1] = gpio_wf[:, 1] + y_offset
                    ax.step(gpio_wf[:, 0], gpio_wf[:, 1], label=gpio_name2)
                    x_offset = time_start + 0.02 * (time_stop - time_start)
                    plt.text(x_offset, y_offset + 0.4, gpio_name2, size="medium", alpha=0.7)
            ax.set_ylim(-0.2, 1.2 * gpio_count + 0.2)
            ax.set_xlabel("time [s]")
            ax.set_ylabel("gpio_level [n]")
            ax.get_yaxis().get_major_formatter().set_useOffset(False)
            ax.get_xaxis().get_major_formatter().set_useOffset(False)
            ax.set_yticks([])
            fig.suptitle("GPIO-Trace")
            if plot_live_view:
                plt.ion()
                plt.show(block=True)
            else:
                file_img = file.with_suffix(".singleAxis.png")
                if file_img.exists():
                    file_img.unlink()
                fig.savefig(file_img)
                plt.close()
