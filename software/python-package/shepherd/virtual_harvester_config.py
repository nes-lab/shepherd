from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Optional
from typing import TypeVar

import yaml
from shepherd_core import CalibrationHarvester

logger = logging.getLogger("shp.hrvConfig")

# Currently implemented harvesters
# NOTE: numbers have meaning and will be tested ->
# - harvesting on "neutral" is not possible
# - emulation with "ivcurve" or lower is also resulting in Error
# - "_opt" has its own algo for emulation, but is only a fast mppt_po for harvesting
algorithms = {
    "neutral": 2**0,
    "isc_voc": 2**3,
    "ivcurve": 2**4,
    "cv": 2**8,
    # "ci": 2**9, # is this desired?
    "mppt_voc": 2**12,
    "mppt_po": 2**13,
    "mppt_opt": 2**14,
}


class VirtualHarvesterConfig:
    """TODO: this class is very similar to virtual_source_data, could share a base-class

    :param setting: harvester-config as name, path to yaml or already usable as dict
    :param samplerate_sps:
    :param emu_cfg: optional config-dict (needed for emulation) with:
        - dtype: datatype of input-file
        - window_samples: complete length of the ivcurve (if applicable)
          -> steps * (1 + wait_cycles)
    """

    name: str = "vHarvester"
    _dtype_default: str = "ivcurve"  # fallback in case of Setting = None
    _def_file = "virtual_harvester_defs.yml"
    _cal = CalibrationHarvester()

    def __init__(
        self,
        setting: Optional[T_vHrv] = None,
        samplerate_sps: int = 100_000,
        emu_cfg: Optional[dict[str, float]] = None,
    ):
        self.samplerate_sps = samplerate_sps
        self.for_emulation = emu_cfg is not None
        def_path = Path(__file__).parent.resolve() / self._def_file
        with open(def_path) as def_data:
            self._config_defs = yaml.safe_load(def_data)["harvesters"]
            self._config_base = self._config_defs["neutral"]
        self._inheritance = []

        if isinstance(setting, str) and Path(setting).exists():
            setting = Path(setting)
        if (
            isinstance(setting, Path)
            and setting.exists()
            and setting.is_file()
            and setting.suffix in [".yaml", ".yml"]
        ):
            self._inheritance.append(str(setting))
            with open(setting) as config_data:
                setting = yaml.safe_load(config_data)["harvesters"]
        if isinstance(setting, str):
            if setting in self._config_defs:
                self._inheritance.append(setting)
                setting = self._config_defs[setting]
            else:
                raise NotImplementedError(
                    f"[{self.name}] Config was set to '{setting}', "
                    f"but definition missing in '{self._def_file}'",
                )

        self.data: dict = {}
        self.data_min: dict = {}
        if setting is None:
            self._inheritance.append(self._dtype_default)
            self.data = self._config_defs[self._dtype_default]
        elif isinstance(setting, VirtualHarvesterConfig):
            self._inheritance.append(self.name + "-Element")
            self.data = setting.data
            self.data_min = setting.data_min
            self.samplerate_sps = setting.samplerate_sps
            self.for_emulation = setting.for_emulation
        elif isinstance(setting, dict):
            self._inheritance.append("parameter-dict")
            self.data = setting
        else:
            raise NotImplementedError(
                f"[{self.name}] {type(setting)}'{setting}' could not be handled. "
                f"In case of file-path -> does it exist?",
            )

        if isinstance(emu_cfg, dict):
            for element in ["dtype", "window_samples"]:
                if element in emu_cfg:
                    self.data[element] = emu_cfg[element]
                else:
                    raise TypeError(
                        f"[{self.name}] Config from Input-File was faulty ({element} missing)",
                    )

            if self.data["dtype"] == "isc_voc":
                raise TypeError(
                    f"[{self.name}] vHarvester can't handle 'isc_voc' format during emulation yet",
                )

        if self.data_min is None:
            self.data_min = copy.copy(self.data)

        self._check_and_complete()
        logger.debug(
            "%s initialized with the following inheritance-chain: '%s'",
            self.name,
            self._inheritance,
        )

    def _check_and_complete(self, verbose: bool = True):
        base_name = self.data.get("base", "neutral")  # 2nd val = default if key missing

        if base_name in self._inheritance:
            raise ValueError(
                f"[{self.name}] loop detected in 'base'-inheritance-system "
                f"@ '{base_name}' already in {self._inheritance}",
            )
        else:
            self._inheritance.append(base_name)

        if base_name == "neutral":
            # root of recursive completion
            self._config_base = self._config_defs[base_name]
            logger.debug("Parameter-Set will be completed with base = '%s'", base_name)
            verbose = False
        elif base_name in self._config_defs:
            config_stash = self.data
            self.data = self._config_defs[base_name]
            logger.debug("Parameter-Set will be completed with base = '%s'", base_name)
            self._check_and_complete(verbose=False)
            self._config_base = self.data
            self.data = config_stash
        else:
            raise NotImplementedError(
                f"[{self.name}] converter-base '{base_name}' is unknown to system",
            )

        self.data["algorithm_num"] = 0
        for base in self._inheritance:
            if base in algorithms:
                self.data["algorithm_num"] += algorithms[base]
        self._check_num("algorithm_num", verbose=verbose)

        self._check_num(
            "window_size",
            16,
            2_000,
            verbose=verbose,
        )  # TODO: why this narrow limit?

        self._check_num("voltage_min_mV", 0, 5_000, verbose=verbose)
        self._check_num(
            "voltage_max_mV",
            self.data["voltage_min_mV"],
            5_000,
            verbose=verbose,
        )
        self._check_num(
            "voltage_mV",
            self.data["voltage_min_mV"],
            self.data["voltage_max_mV"],
            verbose=verbose,
        )

        current_limit_uA = 10**6 * self._cal.adc_C_Hrv.raw_to_si(4)
        self._check_num("current_limit_uA", current_limit_uA, 50_000, verbose=verbose)

        if "voltage_step_mV" not in self.data:
            self.data["voltage_step_mV"] = (
                abs(self.data["voltage_max_mV"] - self.data["voltage_min_mV"])
                / self.data["window_size"]
            )
        v_step_min_mV = 10**3 * self._cal.dac_V_Hrv.raw_to_si(4)
        self._check_num("voltage_step_mV", v_step_min_mV, 1_000_000, verbose=verbose)

        self._check_num("setpoint_n", 0, 1, verbose=verbose)

        self._check_num("rising", 0, 1, verbose=verbose)
        self.data["hrv_mode"] = 1 * (self.for_emulation > 0) + 2 * (self.data["rising"])

        self._check_num("wait_cycles", 0, 100, verbose=verbose)

        # factor-in timing-constraints
        _window_samples = self.data["window_size"] * (1 + self.data["wait_cycles"])

        time_min_ms = (1 + self.data["wait_cycles"]) * 1_000 / self.samplerate_sps
        if self.for_emulation:
            window_ms = _window_samples * 1_000 / self.samplerate_sps
            time_min_ms = max(time_min_ms, window_ms)

        self._check_num(
            "interval_ms",
            0.01,
            1_000_000,
            verbose=verbose,
        )  # creates param if missing
        self._check_num(
            "duration_ms",
            0.01,
            1_000_000,
            verbose=verbose,
        )  # creates param if missing
        ratio_old = self.data["duration_ms"] / self.data["interval_ms"]
        self._check_num("interval_ms", time_min_ms, 1_000_000, verbose=verbose)
        self._check_num(
            "duration_ms",
            time_min_ms,
            self.data["interval_ms"],
            verbose=verbose,
        )
        ratio_new = self.data["duration_ms"] / self.data["interval_ms"]
        if (ratio_new / ratio_old - 1) > 0.1:
            logger.debug(
                "Ratio between interval & duration has changed "
                "more than 10%% due to constraints, from %.4f to %.4f",
                ratio_old,
                ratio_new,
            )

        if "dtype" not in self.data and "dtype" in self._config_base:
            self.data["dtype"] = self._config_base["dtype"]

        # for proper emulation and harvesting (this var decides how h5-file is treated)
        if "window_samples" not in self.data:
            self.data["window_samples"] = _window_samples
        if (
            self.for_emulation
            and (self.data["window_samples"] > 0)
            and (_window_samples > self.data["window_samples"])
        ):
            # TODO: verify that this works ->
            #  if window_samples are zero (set from datalog-reader) they should
            #  stay zero to disable hrv-routine during emulation
            self.data["window_samples"] = _window_samples
        if verbose:
            logger.debug("window_samples = %d", self.data["window_samples"])

    def _check_num(
        self,
        setting_key: str,
        min_value: float = 0,
        max_value: float = 2**32 - 1,
        verbose: bool = True,
    ) -> None:
        try:
            set_value = self.data[setting_key]
        except KeyError:
            set_value = self._config_base[setting_key]
            if verbose:
                logger.debug(
                    "Param '%s' not provided, set to inherited value = %s",
                    setting_key,
                    set_value,
                )
        if (min_value is not None) and (set_value < min_value):
            if verbose:
                logger.debug(
                    "Param %s = %s, but must be >= %s -> adjusted",
                    setting_key,
                    set_value,
                    min_value,
                )
            set_value = min_value
        if (max_value is not None) and (set_value > max_value):
            if verbose:
                logger.debug(
                    "Param %s = %s, but must be <= %s -> adjusted",
                    setting_key,
                    set_value,
                    max_value,
                )
            set_value = max_value
        if not isinstance(set_value, (int, float)) or (set_value < 0):
            raise NotImplementedError(
                f"[{self.name}] '{setting_key}' must a single positive number, "
                f"but is '{set_value}'",
            )
        self.data[setting_key] = set_value

    def export_for_sysfs(self) -> list:
        """prepares virtconverter settings for PRU core (a lot of unit-conversions)

        This Fn add values in correct order and convert to requested unit

        Returns:
            int-list (2nd level for LUTs) that can be feed into sysFS
        """
        if self.for_emulation and self.data["algorithm_num"] <= algorithms["ivcurve"]:
            raise ValueError(
                f"[{self.name}] Select valid harvest-algorithm for emulator, "
                f"current usage = {self._inheritance}",
            )
        elif self.data["algorithm_num"] < algorithms["ivcurve"]:
            raise ValueError(
                f"[{self.name}] Select valid harvest-algorithm for harvester, "
                f"current usage = {self._inheritance}",
            )

        setlist = [
            int(self.data["algorithm_num"]),
            int(self.data["hrv_mode"]),  # bit-field
            round(
                self.data["window_samples"]
                if self.for_emulation
                else self.data["window_size"],
            ),
            round(self.data["voltage_mV"] * 1e3),  # uV
            round(self.data["voltage_min_mV"] * 1e3),  # uV
            round(self.data["voltage_max_mV"] * 1e3),  # uV
            round(self.data["voltage_step_mV"] * 1e3),  # uV
            round(self.data["current_limit_uA"] * 1e3),  # nA
            round(
                max(0, min(255, self.data["setpoint_n"] * 256)),
            ),  # n8 -> 0..1 is mapped to 0..255
            round(
                self.data["interval_ms"] * self.samplerate_sps // 10**3,
            ),  # n, samples
            round(
                self.data["duration_ms"] * self.samplerate_sps // 10**3,
            ),  # n, samples
            round(self.data["wait_cycles"]),  # n, samples
        ]

        return [int(value) for value in setlist]


T_vHrv = TypeVar("T_vHrv", VirtualHarvesterConfig, dict, str, Path)
