import pickle
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from typing_extensions import Self

from .logger import logger


class LogicTrace:
    def __init__(
        self,
        data: np.ndarray,
        *,
        name: str | None = None,
        glitch_ns: int = 0,
    ) -> None:
        self.name: str = name
        # prepare data
        self.channel_count: int = data.shape[1] - 1
        self.data: list = []
        # TODO: analyze & store
        data_ts: np.ndarray = data[:, 0].astype("float64")
        for _i in range(1, data.shape[1]):
            _data = data[:, _i]
            _data = self._convert_analog2digital(_data)
            _data = self._filter_redundant_states(_data, data_ts)
            _data = self._filter_glitches(_data, glitch_ns)
            self.data.append(_data)
        # data = self.filter_cs_falling_edge()

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        glitch_ns: int = 0,
    ) -> Self:
        if not path.exists():
            raise FileNotFoundError()
        if path.with_suffix(".pkl").exists():
            path = path.with_suffix(".pkl")
            # logger.debug("File")
        if path.suffix.lower() == ".csv":
            data: np.ndarray = np.loadtxt(
                path.as_posix(),
                delimiter=",",
                skiprows=1,
            )
            return cls(data, name=path.stem, glitch_ns=glitch_ns)
        if path.suffix.lower() == ".pkl":
            with path.open("rb") as _fh:
                obj = pickle.load(_fh)
            return obj
        raise TypeError(
            f"File must be .csv or .pkl (pickle) - Don't know how to open '{path.name}'"
        )

    def to_file(self, path: Path) -> None:
        if path.is_dir():
            path = path / (self.name + ".pkl")
        with path.open("wb") as _fh:
            pickle.dump(self, _fh)

    @staticmethod
    def _convert_analog2digital(
        data: np.ndarray, *, invert: bool = False
    ) -> np.ndarray:
        """Divide dimension in two, divided by mean-value"""
        _theshold = np.mean(data)
        if invert:
            data = data <= _theshold
        else:
            data = data >= _theshold
        return data.astype("bool")

    @staticmethod
    def _filter_redundant_states(
        data: np.ndarray, timestamps: np.ndarray
    ) -> np.ndarray:
        """Sum of two sequential states is always 1 (True + False) if alternating
        returns timestamps of alternating states, starting with 0
        """
        _d0 = data[:].astype("uint8")
        _d1 = np.concatenate([[not _d0[0]], _d0[:-1]])
        _df = _d0 + _d1
        _ds = timestamps[_df == 1]
        # discard first&last entry AND make sure state=low starts
        if _d0[0] == 0:
            _ds = _ds[2:-1]
        else:
            _ds = _ds[1:-1]
        if len(_d0) > len(_ds):
            logger.debug(
                "filtered out %d/%d events (redundant)",
                len(_d0) - len(_ds),
                len(_d0),
            )
        return _ds

    @staticmethod
    def _filter_glitches(data: np.ndarray, duration_ns: int = 10):
        _diff = ((data[1:] - data[:-1]) * 1e9).astype("uint64")
        _filter1 = _diff > duration_ns
        _filter2 = np.concatenate([_filter1, [True]]) & np.concatenate(
            [[True], _filter1]
        )
        _num = len(_filter1) - _filter1.sum()
        if _num > 0:
            logger.debug("filtered out %d glitches", _num)
        return data[_filter2]

    def calc_durations_ns(
        self, channel: int, edge_a_rising: bool, edge_b_rising: bool
    ) -> np.ndarray:
        _d0 = self.data[channel]
        if edge_b_rising:
            if edge_a_rising:
                _da = _d0[1::2]
                _db = _d0[3::2]
            else:
                _da = _d0[0::2]
                _db = _d0[1::2]
        else:
            if edge_a_rising:
                _da = _d0[1::2]
                _db = _d0[2::2]
            else:
                _da = _d0[0::2]
                _db = _d0[2::2]
        _len = min(len(_da), len(_db))
        _diff = _db[:_len] - _da[:_len]
        return np.column_stack(
            [_da[:_len], _diff * 1e9]
        )  # 2 columns: timestamp, duration [ns]

    def get_edge_timestamps(self, channel: int = 0, rising: bool = True) -> np.ndarray:
        if rising:
            return self.data[channel][1::2]
        else:
            return self.data[channel][0::2]

    @staticmethod
    def calc_duration_free_ns(data_a: np.ndarray, data_b: np.ndarray) -> np.ndarray:
        # correct offset by minimizing it
        off_0 = abs(np.mean(data_b[1:11] - data_a[0:10]))
        off_1 = abs(np.mean(data_b[0:10] - data_a[0:10]))
        off_2 = abs(np.mean(data_b[0:10] - data_a[1:11]))
        if (off_0 <= off_1) & (off_0 <= off_2):
            data_b = data_b[1:]
        if (off_2 <= off_0) & (off_2 <= off_1):
            data_a = data_a[1:]
        # cut data to same length
        _len = min(len(data_a), len(data_b))
        data_a = data_a[:_len]
        data_b = data_b[:_len]
        # calculate duration of offset
        _diff = data_b[:_len] - data_a[:_len]
        return np.column_stack(
            [data_a[:_len], _diff * 1e9]
        )  # 2 columns: timestamp, duration [ns]

    @staticmethod
    def calc_expected_value(data: np.ndarray) -> float:
        """return expected duration (=10**X)"""
        # data with timestamp!
        if data.shape[0] < 100:
            raise ValueError("Function needs more datapoints")
        if data.shape[1] != 2:
            raise ValueError("Function needs matrix with timestamps and durations")
        return 10 ** np.round(np.log10(data[:, 1].mean()))

    @staticmethod
    def get_statistics(data: np.ndarray, name: str) -> list:
        # data with timestamp!
        if data.shape[0] < 100:
            raise ValueError("Function needs more datapoints")
        if data.shape[1] != 2:
            raise ValueError("Function needs matrix with timestamps and durations")
        dmin = data[:, 1].min()
        dmax = data[:, 1].max()
        tmin = (data[data[:, 1] == dmin, 0])[0]
        tmax = (data[data[:, 1] == dmax, 0])[0]
        dmin = round(dmin)
        dmax = round(dmax)
        dq01 = round(np.quantile(data[:, 1], 0.01))
        dq05 = round(np.quantile(data[:, 1], 0.05))
        dq95 = round(np.quantile(data[:, 1], 0.95))
        dq99 = round(np.quantile(data[:, 1], 0.99))
        dmean = round(data[:, 1].mean())
        return [name, dmin, dq01, dq05, dmean, dq95, dq99, dmax, tmin, tmax, dq99 - dq01, dmax - dmin]

    @staticmethod
    def get_statistics_header() -> list:
        return [
            "name",
            "min [ns]",
            "q1 [ns]",
            "q5 [ns]",
            "mean [ns]",
            "q95 [ns]",
            "q99 [ns]",
            "max [ns]",
            "t_min [s]",
            "t_max [s]",
            "q99:1 [ns]",
            "minmax [ns]",
        ]

    @staticmethod
    def plot_series_jitter(
        data: np.ndarray,
        name: str,
        path: Path,
        size: tuple = (18, 8),
        y_side: int = 1000,
    ) -> None:
        # data with timestamp!
        if data.shape[0] < 100:
            raise ValueError("Function needs more datapoints")
        if data.shape[1] != 2:
            raise ValueError("Function needs matrix with timestamps and durations")
        if path.is_dir():
            _path = path / (name + f"_jitter.png")
        else:
            _path = path
        _center = np.median(data[:, 1])
        _range = [_center - y_side, _center + y_side]
        fig, ax = plt.subplots(figsize=size)
        plt.plot(data[:, 0], data[:, 1])  # X,Y
        ax.set_xlabel("time [s]")
        ax.axes.set_ylim(_range)
        ax.axes.set_ylabel("trigger-jitter [ns]")
        ax.axes.set_title(_path.stem)
        fig.savefig(_path)
        plt.close()

    @staticmethod
    def filter_cs_falling_edge(data: pd.Series, falling: bool = True) -> pd.Series:
        # TODO: not finished
        data.columns = data.columns.str.strip()  # fixes weird space before column-names
        # values are binary -> get timestamps of chipselect-start (falling Edge)
        # - first calc the derivative (current value - previous value)
        # - second filter for "-1" and keep only these
        # - now subtract the timestamps
        # data = data[data["Time[s]"] > 1]
        dtime = data["Time[s]"].iloc[1:]
        ch0 = data.loc[:, "Channel 0"]
        ch0d = pd.Series(ch0.values[1:] - ch0.values[:-1], index=ch0.index[1:])
        ch0t = dtime[ch0d < 0]
        ch1 = data.loc[:, "Channel 1"]
        ch1d = pd.Series(ch1.values[1:] - ch1.values[:-1], index=ch1.index[1:])
        ch1t = dtime[ch1d < 0]
        # filter time-series for start and end that both series cover
        time_start = max(ch0t.min(), ch1t.min()) - 5e-6
        time_stop = min(ch0t.max(), ch1t.max()) - 5e-6
        ch0t = ch0t[(ch0t > time_start) & (ch0t < time_stop)].reset_index(drop=True)
        ch1t = ch1t[(ch1t > time_start) & (ch1t < time_stop)].reset_index(drop=True)
        min_length = min(ch0t.shape[0], ch1t.shape[0])
        # cut series to proper length and determine channel offset
        data_new = [
            ch0t.iloc[0:min_length].mul(1e9).round(0),
            ch1t.iloc[0:min_length].mul(1e9).round(0),
        ]
        df = pd.concat(data_new, axis=1)
        df.columns = ["Ch0", "Ch1"]
        return df
