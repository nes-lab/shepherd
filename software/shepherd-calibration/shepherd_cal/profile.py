from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from .logger import logger
from .profile_calibration import ProfileCalibration

component_dict: dict[str, str] = {
    "a": "emu_a",
    "emu_a": "emu_a",
    "b": "emu_b",
    "emu_b": "emu_b",
    "h": "hrv",
    "hrv": "hrv",
}

elem_dict: dict[str, int] = {
    "voltage_shp_V": 0,
    "voltage_shp_raw": 1,
    "voltage_ref_V": 2,
    "current_shp_A": 3,
    "current_shp_raw": 4,
    "current_ref_A": 5,
}
elem_list: list[str] = [
    "v_shp_V",
    "v_shp_raw",
    "v_ref_V",
    "c_shp_A",
    "c_shp_raw",
    "c_ref_A",
]

# TODO: profiler should use CalibrationCape with CalibrationHarvester & CalibrationEmulator


class Profile:
    def __init__(self, file: Path) -> None:
        if not isinstance(file, Path):
            file = Path(file)
        if file.suffix != ".npz":
            # TODO: is this useful?
            file = Path(file.stem + ".npz")

        logger.debug("processing '%s'", file)
        meas_file = np.load(str(file), allow_pickle=True)
        self.file_name: str = file.stem

        self.data: dict[str, pd.DataFrame] = {}
        self.cals: dict[str, ProfileCalibration] = {}

        self.results: dict[str, pd.DataFrame] = {}
        self.stats: list[pd.DataFrame] = []

        self.data_filters: dict[str, pd.Series] = {}
        self.res_filters: dict[str, pd.Series] = {}

        for comp_i in component_dict:
            if comp_i not in meas_file:
                continue
            if (meas_file[comp_i] is None) or (meas_file[comp_i].size < 2):
                continue
            comp_o = component_dict[comp_i]
            logger.debug("  component '%s'", comp_o)

            self._prepare_data(comp_o, meas_file[comp_i])
            # ⤷ changes self.data !
            self._prepare_results(comp_o, self.data[comp_o])
            self._prepare_filters(comp_o)
            self._prepare_stats(comp_o, self.data[comp_o])

    def _prepare_data(self, component: str, data_raw: np.ndarray) -> None:
        data_pandas = pd.DataFrame(np.transpose(data_raw), columns=elem_list)

        # get the inner 100k-array out - similar to pd.ungroup, but without special cmd
        segment_list = []
        for _, row in data_pandas.iterrows():
            # c_shp_raw is always np.array, but v_shp_raw only when
            segment_df = pd.DataFrame(row.c_shp_raw, columns=["c_shp_raw"])
            segment_df["c_ref_A"] = row.c_ref_A
            segment_df["c_shp_A"] = row.c_shp_A
            segment_df["v_ref_V"] = row.v_ref_V
            segment_df["v_shp_V"] = row.v_shp_V
            segment_df["v_shp_raw"] = row.v_shp_raw
            segment_list.append(segment_df)
        data_df = pd.concat(segment_list, axis=0)

        # fragment to fix old profiles
        # -> special case when measuring without SourceMeter, but with resistor
        filter_v = data_df.v_ref_V <= -3
        data_df.loc[filter_v, "v_ref_V"] = data_df.loc[filter_v, "v_shp_V"]
        data_df.loc[filter_v, "c_ref_A"] = data_df.loc[filter_v, "c_shp_A"]

        # fix the known case of missing SMU (PART 1)
        if component == "emu_b" and "emu_a" in self.cals:
            cal = self.cals["emu_a"]
            logger.debug("  -> replaced Cal of emu_b with _a")
        else:
            cal = ProfileCalibration.from_measurement(data_df)

        data_df["c_shp_A"] = cal.current.raw_to_si(data_df.c_shp_raw.to_numpy())
        data_df["c_shp_A"] = data_df.c_shp_A.apply(lambda x: x if x >= -1e-3 else -1e-3)

        # fix the known case of missing SMU (PART 2)
        if component == "emu_b":
            # assume resistor
            resistor = (data_df["v_shp_V"] / data_df["c_shp_A"]).median()
            data_df["c_ref_A"] = data_df["v_shp_V"] / resistor
            data_df["v_ref_V"] = data_df.loc[:, "v_shp_V"]
            logger.debug(
                "  -> replaced SMU-values with shp-values and estimate resistor (%.3f Ohm)",
                resistor,
            )

        data_df["v_error_mV"] = 1e3 * (data_df.v_ref_V - data_df.v_shp_V)
        data_df["v_error_abs_mV"] = data_df.v_error_mV.abs()
        data_df["c_error_mA"] = 1e3 * (data_df.c_ref_A - data_df.c_shp_A)
        data_df["c_error_abs_mA"] = data_df.c_error_mA.abs()

        self.data[component] = data_df
        self.cals[component] = cal

    def _prepare_results(self, component: str, data: pd.DataFrame) -> None:
        result = data.groupby(by=["c_ref_A", "v_shp_V"]).mean().reset_index(drop=False)
        result["v_error_mean_mV"] = (
            data.groupby(by=["c_ref_A", "v_shp_V"])
            .v_error_mV.mean()
            .reset_index(drop=True)
        )
        result["v_error_max_mV"] = (
            data.groupby(by=["c_ref_A", "v_shp_V"])
            .v_error_abs_mV.max()
            .reset_index(drop=True)
        )
        result["v_error_stddev_mV"] = (
            data.groupby(by=["c_ref_A", "v_shp_V"])
            .v_error_abs_mV.std()
            .reset_index(drop=True)
        )
        result["c_error_mean_mA"] = (
            data.groupby(by=["c_ref_A", "v_shp_V"])
            .c_error_mA.mean()
            .reset_index(drop=True)
        )
        result["c_error_max_mA"] = (
            data.groupby(by=["c_ref_A", "v_shp_V"])
            .c_error_abs_mA.max()
            .reset_index(drop=True)
        )
        result["c_error_stddev_mA"] = (
            data.groupby(by=["c_ref_A", "v_shp_V"])
            .c_error_abs_mA.std()
            .reset_index(drop=True)
        )
        self.results[component] = result

    def _prepare_filters(self, component: str) -> None:
        data = self.data[component]
        filter_c = (data["c_ref_A"] >= 3e-6) & (data["c_ref_A"] <= 40e-3)
        filter_v = (data.v_shp_V >= 1.0) & (data.v_shp_V <= 3.9)
        self.data_filters[component] = filter_c & filter_v
        result = self.results[component]
        filter_c = (result.c_ref_A >= 3e-6) & (result.c_ref_A <= 40e-3)
        filter_v = (result.v_shp_V >= 1.0) & (result.v_shp_V <= 3.9)
        self.res_filters[component] = filter_c & filter_v

    def _prepare_stats(self, component: str, data: pd.DataFrame) -> None:
        """Statistics-Generator
        - every dataset is a row
        - v_diff_mean @all, @1-4V;0-40mA, over each voltage + each current
        - v_diff_max @all, @1-4V;0-40mA, over each ...
        - c_error_mean @all, @1-4V;0-40mA -> abs-value?
          min, max, stddev, minmax-intervall, mean

        """
        for decision in [False, True]:
            stat_values = pd.DataFrame()
            result_now = data[self.data_filters[component]] if decision else data
            stat_values["origin"] = [self.file_name]  # Note: first entry must be in []
            stat_values["component"] = component.upper()
            stat_values["range"] = "limited" if decision else "full"

            stat_values["v_error_mean_mV"] = result_now.v_error_abs_mV.mean()
            stat_values["v_error_max_mV"] = result_now.v_error_abs_mV.max()
            stat_values["v_error_std_mV"] = result_now.v_error_abs_mV.std()

            stat_values["c_error_mean_mA"] = result_now.c_error_abs_mA.mean()
            stat_values["c_error_max_mA"] = result_now.c_error_abs_mA.max()
            stat_values["c_error_std_mA"] = result_now.c_error_abs_mA.std()
            self.stats.append(stat_values)

    def get_stats(self) -> pd.DataFrame:
        return pd.concat(self.stats, axis=0, ignore_index=True)

    def scatter_setpoints_stddev(self, component: str, filtered: bool = False) -> None:
        data = self.results[component]
        if filtered:
            data = data[self.res_filters[component]]
        filter_str = "_filtered" if filtered else ""
        c_gain = self.cals[component].current.gain
        x = 1e3 * data.v_ref_V  # todo: transition not finished, same with above FN
        y = []
        stddev = []
        vol = []
        for i in range(data.shape[1]):
            y.append(1e3 * data[elem_dict["current_shp_A"], i])
            value = 1e6 * c_gain * np.std(data[elem_dict["current_shp_raw"], i])
            stddev.append(value)
            vol.append(25 * value)

        fig, ax = plt.subplots()
        sct = ax.scatter(x, y, c=stddev, s=vol, cmap="turbo", alpha=0.7)

        ax.set_xlabel(r"Voltage [mV]", fontsize=10)
        ax.set_ylabel(r"Current [mA]", fontsize=10)
        ax.set_title(
            "Position of Setpoints with Standard-Deviation as color/size "
            f"(mean = {np.mean(stddev):.2f} uA)",
        )
        plt.colorbar(
            sct,
            label="Standard-Deviation [uA]",
            orientation="vertical",
            shrink=0.7,
        )
        ax.grid(True)
        ax.set_xlim(-500, 5000)
        ax.set_ylim(-5, 50)
        fig.set_figwidth(11)
        fig.set_figheight(10)
        fig.tight_layout()
        plt.savefig(
            self.file_name + "_scatter_stddev_" + component + filter_str + ".png",
        )
        plt.close(fig)
        plt.clf()

    def scatter_setpoints_dynamic(self, component: str, filtered: bool = False) -> None:
        data = self.results[component]
        if filtered:
            data = data[self.res_filters[component]]
        filter_str = "_filtered" if filtered else ""
        c_gain = self.cals[component].current.gain
        x = 1e3 * data[elem_dict["voltage_ref_V"], :]
        raise ValueError("Test ME")
        # TODO: can probably be data[elem_dict["voltage_ref_V"]],
        y = []
        dyn = []
        vol = []
        for i in range(data.shape[1]):
            y.append(1e3 * data[elem_dict["current_shp_A"], i])
            value = (
                1e6
                * c_gain
                * (
                    np.max(data[elem_dict["current_shp_raw"], i])
                    - np.min(data[elem_dict["current_shp_raw"], i])
                )
            )
            dyn.append(value)
            vol.append(5 * value)

        fig, ax = plt.subplots()
        sct = ax.scatter(x, y, c=dyn, s=vol, cmap="turbo", alpha=0.7)

        ax.set_xlabel(r"Voltage [mV]", fontsize=10)
        ax.set_ylabel(r"Current [mA]", fontsize=10)
        ax.set_title(
            "Position of Setpoints with ADC-MinMax-Intervall as color/size "
            f"(mean = {np.mean(dyn):.2f} uA)",
        )
        plt.colorbar(
            sct,
            label="ADC-MinMax-Intervall [uA]",
            orientation="vertical",
            shrink=0.7,
        )

        ax.grid(True)
        ax.set_xlim(-500, 5000)
        ax.set_ylim(-5, 50)
        fig.set_figwidth(11)
        fig.set_figheight(10)
        fig.tight_layout()
        plt.savefig(
            self.file_name + "_scatter_dynamic_" + component + filter_str + ".png",
        )
        plt.close(fig)
        plt.clf()

    def quiver_setpoints_offset(self, component: str, filtered: bool = False) -> None:
        data = self.results[component]
        if filtered:
            data = data[self.res_filters[component]]
        filter_str = "_filtered" if filtered else ""
        fig, ax = plt.subplots()
        ax.scatter(
            1e3 * data.v_shp_V,
            1e3 * data.c_ref_A,
            c=1e3 * data.c_error_mean_mA,
            s=10,
            alpha=0.7,
            cmap="turbo",
        )
        qpl = ax.quiver(
            1e3 * data.v_shp_V,
            1e3 * data.c_ref_A,  # XY
            data.v_error_mean_mV,
            data.c_error_mean_mA,  # UV
            1e3 * data.c_error_mean_mA,  # W
            units="xy",
            scale=1,
            pivot="tail",
            cmap="turbo",
            alpha=0.9,
        )  # pivot: tail, mid, tip
        ax.set_xlabel(r"Voltage [mV]", fontsize=10)
        ax.set_ylabel(r"Current [mA]", fontsize=10)
        ax.set_title("Position of Setpoints with Distance from Ref")
        plt.colorbar(
            qpl,
            label="Error (mean) of Current [uA]",
            orientation="vertical",
            shrink=0.7,
        )

        ax.grid(True)
        ax.set_xlim(-500, 5500)
        ax.set_ylim(-5, 55)
        fig.set_figwidth(11)
        fig.set_figheight(10)
        fig.tight_layout()
        plt.savefig(self.file_name + "_quiver_" + component + filter_str + ".png")
        plt.close(fig)
        plt.clf()
