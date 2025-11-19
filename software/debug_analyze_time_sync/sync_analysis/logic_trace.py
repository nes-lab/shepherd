import pickle
from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from typing_extensions import Self

from .logger import log


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
        data_ts: np.ndarray = data[:, 0].astype(np.float64)
        for _i in range(1, data.shape[1]):
            data_ = data[:, _i]
            data_ = self._convert_analog2digital(data_)
            data_ = self._filter_redundant_states(data_, data_ts)
            data_ = self._filter_glitches(data_, glitch_ns)
            self.data.append(data_)
        # data = self.filter_cs_falling_edge()

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        glitch_ns: int = 0,
    ) -> Self:
        if not path.exists():
            raise FileNotFoundError
        if path.with_suffix(".pkl").exists():
            path = path.with_suffix(".pkl")
            # log.debug("File")
        if path.suffix.lower() == ".csv":
            data: np.ndarray = np.loadtxt(
                path.as_posix(),
                delimiter=",",
                skiprows=1,
            )
            return cls(data, name=path.stem, glitch_ns=glitch_ns)
        if path.suffix.lower() == ".pkl":
            with path.open("rb") as _fh:
                return pickle.load(_fh)

        msg = f"File must be .csv or .pkl (pickle) - Don't know how to open '{path.name}'"
        raise TypeError(msg)

    def to_file(self, path: Path) -> None:
        if path.is_dir():
            path /= self.name + ".pkl"
        path.with_suffix(".pkl")
        with path.open("wb") as _fh:
            pickle.dump(self, _fh)

    @staticmethod
    def _convert_analog2digital(
        data: np.ndarray,
        *,
        invert: bool = False,
    ) -> np.ndarray:
        """Divide dimension in two, divided by mean-value."""
        threshold = np.mean(data)
        data = (data <= threshold) if invert else (data >= threshold)
        return data.astype("bool")

    @staticmethod
    def _filter_redundant_states(
        data: np.ndarray,
        timestamps: np.ndarray,
    ) -> np.ndarray:
        """Sum of two sequential states is always 1 (True + False) if alternating.

        -> returns timestamps of alternating states, starting with 0.
        """
        d0_ = data[:].astype(np.uint8)
        d1_ = np.concatenate([[not d0_[0]], d0_[:-1]])
        df_ = d0_ + d1_
        ds_ = timestamps[df_ == 1]
        # discard first&last entry AND make sure state=low starts
        ds_ = ds_[2:-1] if (d0_[0] == 0) else ds_[1:-1]
        if len(d0_) > len(ds_):
            log.debug(
                "filtered out %d/%d events (redundant)",
                len(d0_) - len(ds_),
                len(d0_),
            )
        return ds_

    @staticmethod
    def _filter_glitches(data: np.ndarray, duration_ns: int = 10) -> np.ndarray:
        diff_ = ((data[1:] - data[:-1]) * 1e9).astype(np.uint64)
        filter1 = diff_ > duration_ns
        filter2 = np.concatenate([filter1, [True]]) & np.concatenate(
            [[True], filter1],
        )
        num_ = len(filter1) - filter1.sum()
        if num_ > 0:
            log.debug("filtered out %d glitches", num_)
        return data[filter2]

    def calc_durations_ns(
        self,
        channel: int,
        *,
        edge_a_rising: bool,
        edge_b_rising: bool,
    ) -> np.ndarray:
        d0_ = self.data[channel]
        if edge_b_rising:
            if edge_a_rising:
                da_ = d0_[1::2]
                db_ = d0_[3::2]
            else:
                da_ = d0_[0::2]
                db_ = d0_[1::2]
        elif edge_a_rising:
            da_ = d0_[1::2]
            db_ = d0_[2::2]
        else:
            da_ = d0_[0::2]
            db_ = d0_[2::2]
        len_ = min(len(da_), len(db_))
        diff_ = db_[:len_] - da_[:len_]
        return np.column_stack(
            [da_[:len_], diff_ * 1e9],
        )  # 2 columns: timestamp, duration [ns]

    def get_edge_timestamps(self, channel: int = 0, *, rising: bool = True) -> np.ndarray:
        if rising:
            return self.data[channel][1::2]
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
        len_ = min(len(data_a), len(data_b))
        data_a = data_a[:len_]
        data_b = data_b[:len_]
        # calculate duration of offset
        diff_ = data_b[:len_] - data_a[:len_]
        return np.column_stack(
            [data_a[:len_], diff_ * 1e9],
        )  # 2 columns: timestamp, duration [ns]

    @staticmethod
    def calc_expected_value(data: np.ndarray, *, mode_log10: bool = False) -> float:
        """Return expected duration (=10**X)."""
        # data with timestamp!
        if data.shape[0] < 100:
            raise ValueError("Function needs more datapoints")
        if data.shape[1] != 2:
            raise ValueError("Function needs matrix with timestamps and durations")
        if mode_log10:
            return 10 ** np.round(np.log10(data[:, 1].mean()))
        # 1 us resolution
        return 1000 * np.round(data[:, 1].mean() / 1000)

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
        dq01 = round(np.quantile(data[:, 1], 0.01))
        dq05 = round(np.quantile(data[:, 1], 0.05))
        dq95 = round(np.quantile(data[:, 1], 0.95))
        dq99 = round(np.quantile(data[:, 1], 0.99))
        dmean = round(data[:, 1].mean())
        return [
            name,
            round(dmin),
            dq01,
            dq05,
            dmean,
            dq95,
            dq99,
            round(dmax),
            tmin,
            tmax,
            round(dq99 - dq01),
            round(dmax - dmin),
        ]

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
            "Δ_q1 [ns]",
            "Δ_max [ns]",
        ]

    @staticmethod
    def plot_series_jitter(
        data: np.ndarray,
        name: str,
        path: Path,
        size: Sequence = (18, 8),
        y_side: int = 1000,
    ) -> None:
        # data with timestamp!
        if data.shape[0] < 100:
            raise ValueError("Function needs more datapoints")
        if data.shape[1] != 2:
            raise ValueError("Function needs matrix with timestamps and durations")

        path_ = path / (name + "_jitter.png") if path.is_dir() else path

        center_ = np.median(data[:, 1])
        range_ = [center_ - y_side, center_ + y_side]
        fig, ax = plt.subplots(figsize=size)
        plt.plot(data[:, 0], data[:, 1])  # X,Y
        ax.set_xlabel("time [s]")
        ax.axes.set_ylim(range_)
        ax.axes.set_ylabel("trigger-jitter [ns]")
        ax.axes.set_title(path_.stem)
        fig.savefig(path_)
        plt.close()
