import pickle
from pathlib import Path
from typing import Self, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .filesystem import get_files
from .logic_trace import LogicTrace
from .logger import logger


class LogicTraces:

    def __init__(
            self,
            path: Path,
    ) -> None:
        self.traces: list[LogicTrace] = []
        _fcsv = get_files(path, suffix=".csv")

        for _f in _fcsv:
            self.traces.append(LogicTrace.from_file(_f))

    def plot_comparison_series(self, start: int = 0) -> None:
        _names: list = [_t.name for _t in self.traces]
        _data: list = [pd.Series(_t.calc_durations_ns(0, True, True)) for _t in self.traces]
        _len = len(_names)
        _names = _names[start:]
        _data = _data[start:]
        # TODO: this just takes first CH0
        # file_names_short.reverse()
        fig_title = f"improvement_trigger_statistics_boxplot_{start}to{_len}"
        df = pd.concat(_data, axis=1)
        df.columns = _names
        ax = df.plot.box(figsize=(20, 8), return_type="axes")
        ax.set_ylabel("trigger_delay [ns]")
        ax.set_title(fig_title)
        plt.grid(True, which="major", axis="y", color="grey", linewidth="0.6", linestyle=":", alpha=0.8)
        plt.savefig(fig_title + ".png")
        plt.close()

