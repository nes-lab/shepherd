from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .logger import log
from .logic_trace import LogicTrace


class LogicTraces:
    def __init__(
        self,
        path: Path,
        glitch_ns: int = 0,
    ) -> None:
        self.traces: list[LogicTrace] = []
        fcsv_ = list(path.rglob("*.csv"))
        log.debug(" -> got %s csv-files", len(fcsv_))

        for _f in fcsv_:
            self.traces.append(LogicTrace.from_file(_f, glitch_ns=glitch_ns))

    def plot_comparison_series(self, start: int = 0) -> None:
        names_: list = [_t.name for _t in self.traces]
        data_: list = [
            _t.calc_durations_ns(0, edge_a_rising=True, edge_b_rising=True) for _t in self.traces
        ]
        data_ = [pd.Series(data[:, 1] - LogicTrace.calc_expected_value(data)) for data in data_]

        len_ = len(names_)
        names_ = names_[start:]
        data_ = data_[start:]

        if len(names_) < 1 or len(data_) < 1:
            return
        # TODO: this just takes first CH0
        # file_names_short.reverse()
        fig_title = f"improvement_trigger_statistics_boxplot_{start}to{len_}"
        # TODO: could also print a histogram-overlay for some
        df_ = pd.concat(data_, axis=1)
        df_.columns = names_
        ax = df_.plot.box(
            figsize=(20, 8),
            return_type="axes",
            ylim=[-10_000, 10_000],
            # ylim=[-1_000, +1_000], TODO: make it variable
        )
        ax.set_ylabel("trigger_delay [ns]")
        ax.set_title(fig_title)
        plt.grid(
            visible=True,
            which="major",
            axis="y",
            color="gray",
            linewidth="0.6",
            linestyle=":",
            alpha=0.8,
        )
        plt.savefig(fig_title + ".png")
        plt.close()
