from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Optional
from typing import TypeVar

import yaml

logger = logging.getLogger("shp.srcConfig")


def flatten_list(dl: list) -> list:
    """small helper FN to convert (multi-dimensional) lists to 1D list

    Args:
        dl: (multi-dimensional) lists
    Returns:
        1D list
    """
    if isinstance(dl, list):
        if len(dl) < 1:
            return dl
        if len(dl) == 1:
            if isinstance(dl[0], list):
                return flatten_list(dl[0])
            else:
                return dl
        elif isinstance(dl[0], list):
            return flatten_list(dl[0]) + flatten_list(dl[1:])
        else:
            return [dl[0]] + flatten_list(dl[1:])
    else:
        return [dl]


class VirtualSourceConfig:
    """
    Container for VS Settings, Data will be checked and completed
    - settings will be created from default values when omitted
    - internal settings are derived from existing values (PRU has no FPU, so it is done here)
    - settings can be exported in required format
    - NOTES to naming:
        - virtual harvester -> used for harvester and emulator, contains tools to
                            characterize (ivcurve) and harvest these energy-sources (mppt)
        - virtual converter -> buck-boost, diode and other converters to supply the target
        - virtual source -> container for harvester + converter
    """

    name: str = "vSource"
    _def_file = "virtual_source_defs.yml"

    def __init__(
        self,
        setting: Optional[T_vSrc] = None,
        samplerate_sps: int = 100_000,
        log_intermediate_voltage: Optional[bool] = None,
    ):
        """Container for VS Settings, Data will be checked and completed

        Args:
            setting: if omitted, the data is generated from default values
        """
        self.samplerate_sps: int = samplerate_sps

        def_path = Path(__file__).parent.resolve() / self._def_file
        with open(def_path) as def_data:
            self._config_defs = yaml.safe_load(def_data)["virtsources"]
            self._config_base = self._config_defs["neutral"]
        self._inheritance: list[str] = []

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
                setting = yaml.safe_load(config_data)["virtsource"]
        if isinstance(setting, str):
            if setting in self._config_defs:
                self._inheritance.append(setting)
                setting = self._config_defs[setting]
            else:
                raise NotImplementedError(
                    f"[{self.name}] was set to '{setting}', "
                    f"but definition missing in '{self._def_file}'",
                )

        self.data_min: Optional[dict] = None
        if setting is None:
            self.data: dict = {}
        elif isinstance(setting, VirtualSourceConfig):
            # TODO: replace by .from_instance() below
            self._inheritance.append(self.name + "-Element")
            self.data = setting.data
            self.data_min = setting.data_min
            self.samplerate_sps = setting.samplerate_sps
        elif isinstance(setting, dict):
            self._inheritance.append("parameter-dict")
            self.data = setting
        else:
            raise NotImplementedError(
                f"[{self.name}] InputSetting could not be handled. "
                f"In case of file-path -> does it exist? \n"
                f"\t type = '{type(setting)}', \n"
                f"\t content = '{setting}'",
            )

        if log_intermediate_voltage is not None:
            self.data["log_intermediate_voltage"] = log_intermediate_voltage

        if self.data_min is None:
            self.data_min = copy.copy(self.data)

        self.check_and_complete()

        logger.debug(
            "%s initialized with the following inheritance-chain: '%s'",
            self.name,
            self._inheritance,
        )

    @classmethod
    def from_instance(cls, instance):  # type: ignore
        vsrc: VirtualSourceConfig = instance
        vsrc._inheritance.append(vsrc.name + "-Element")
        vsrc.check_and_complete()

    def export_for_sysfs(self) -> list:
        """prepares virtual-converter settings for PRU core (a lot of unit-conversions)

        The current emulator in PRU relies on the virtual-converter settings.
        This Fn add values in correct order and convert to requested unit

        Returns:
            int-list (2nd level for LUTs) that can be feed into sysFS
        """
        return [
            # General
            int(self.data["converter_mode"]),
            round(
                self.data["interval_startup_delay_drain_ms"]
                * self.samplerate_sps
                // 10**3,
            ),  # n, samples
            round(self.data["V_input_max_mV"] * 1e3),  # uV
            round(self.data["I_input_max_mA"] * 1e6),  # nA
            round(self.data["V_input_drop_mV"] * 1e3),  # uV
            round(self.data["R_input_kOhm_n22"] * 1),
            round(self.data["Constant_us_per_nF_n28"]),  # us/nF = us*V / nA*s
            round(self.data["V_intermediate_init_mV"] * 1e3),  # uV
            round(self.data["I_intermediate_leak_nA"] * 1),  # nA
            round(self.data["V_enable_output_threshold_mV"] * 1e3),  # uV
            round(self.data["V_disable_output_threshold_mV"] * 1e3),  # uV
            round(self.data["dV_enable_output_mV"] * 1e3),  # uV
            round(
                self.data["interval_check_thresholds_ms"]
                * self.samplerate_sps
                // 10**3,
            ),  # n, samples
            round(self.data["V_pwr_good_enable_threshold_mV"] * 1e3),  # uV
            round(self.data["V_pwr_good_disable_threshold_mV"] * 1e3),  # uV
            round(self.data["immediate_pwr_good_signal"] > 0),  # bool
            round(self.data["V_output_log_gpio_threshold_mV"] * 1e3),  # uV
            # Boost
            round(self.data["V_input_boost_threshold_mV"] * 1e3),  # uV
            round(self.data["V_intermediate_max_mV"] * 1e3),  # uV
            # Buck
            round(self.data["V_output_mV"] * 1e3),  # uV
            round(self.data["V_buck_drop_mV"] * 1e3),  # uV
            # LUTs
            round(self.data["LUT_input_V_min_log2_uV"]),  #
            round(self.data["LUT_input_I_min_log2_nA"]),  #
            round(self.data["LUT_output_I_min_log2_nA"]),  #
            # reduce resolution to n8 to fit in container
            [
                min(255, round(256 * value)) if (value > 0) else 0
                for value in self.data["LUT_input_efficiency"]
            ],
            # is now n4 -> resulting value for PRU is inverted, so 2^4 / value,
            # inv-max = 2^14 for min-value = 1/1024
            [
                min((2**14), round((2**4) / value)) if (value > 0) else int(2**14)
                for value in self.data["LUT_output_efficiency"]
            ],
        ]

    def calculate_internal_states(self) -> None:
        """
        add the following internal variables:
        - converter_mode
        - Constant_us_per_nF_n28
        - dV_enable_output_mV
        - V_enable_output_threshold_mV
        - V_disable_output_threshold_mV
        """
        # assembles bitmask from discrete values
        self.data["converter_mode"] = 0
        enable_storage = self.data["C_intermediate_uF"] > 0
        self.data["converter_mode"] += 1 if enable_storage else 0
        enable_boost = self.data["enable_boost"] and enable_storage
        self.data["converter_mode"] += 2 if enable_boost else 0
        self.data["converter_mode"] += 4 if (self.data["enable_buck"] > 0) else 0
        self.data["converter_mode"] += (
            8 if (self.data["log_intermediate_voltage"] > 0) else 0
        )

        # calc constant to convert capacitor-current to Voltage-delta
        # dV[uV] = constant[us/nF] * current[nA] = constant[us*V/nAs] * current[nA]
        C_storage_uF = max(self.data["C_intermediate_uF"], 0.001)
        self.data["Constant_us_per_nF_n28"] = (10**3 * (2**28)) // (
            C_storage_uF * self.samplerate_sps
        )

        """
        compensate for (hard to detect) current-surge of real capacitors
        when converter gets turned on -> this can be const value, because
        the converter always turns on with "V_storage_enable_threshold_uV"
        TODO: currently neglecting: delay after disabling converter, boost
        only has simpler formula, second enabling when V_Cap >= V_out

        Math behind this calculation:
        Energy-Change Storage Cap   ->  E_new = E_old - E_output
        with Energy of a Cap 	    -> 	E_x = C_x * V_x^2 / 2
        combine formulas 		    ->
                    C_store * V_store_new^2 / 2 = C_store * V_store_old^2 / 2 - C_out * V_out^2 / 2
        convert formula to V_new 	->	V_store_new^2 = V_store_old^2 - (C_out / C_store) * V_out^2
        convert into dV	 	        ->	dV = V_store_new - V_store_old
        in case of V_cap = V_out 	-> 	dV = V_store_old * (sqrt(1 - C_out / C_store) - 1)
        -> dV values will be reversed (negated), because dV is always negative (Voltage drop)
        """
        v_old = self.data["V_intermediate_enable_threshold_mV"]
        v_out = self.data["V_output_mV"]
        c_store = self.data["C_intermediate_uF"]
        c_out = self.data["C_output_uF"]
        if c_store > 0 and c_out > 0:
            # first case: storage cap outside of en/dis-thresholds
            dV_output_en_thrs_mV = v_old - pow(
                pow(v_old, 2) - (c_out / c_store) * pow(v_out, 2),
                0.5,
            )

            # second case: storage cap below v_out (only different for enabled buck),
            #              enable when >= v_out
            # v_enable is either bucks v_out or same dV-Value is calculated a second time
            dV_output_imed_low_mV = v_out * (1 - pow(1 - c_out / c_store, 0.5))
        else:
            dV_output_en_thrs_mV = 0
            dV_output_imed_low_mV = 0

        # protect from complex solutions (non valid input combinations)
        if not (
            isinstance(dV_output_en_thrs_mV, (int, float))
            and (dV_output_en_thrs_mV >= 0)
        ):
            dV_output_en_thrs_mV = 0
        if not (
            isinstance(dV_output_imed_low_mV, (int, float))
            and (dV_output_imed_low_mV >= 0)
        ):
            dV_output_imed_low_mV = 0

        # decide which hysteresis-thresholds to use for buck-converter
        if self.data["enable_buck"] > 0:
            V_pre_output_mV = self.data["V_output_mV"] + self.data["V_buck_drop_mV"]

            if self.data["V_intermediate_enable_threshold_mV"] > V_pre_output_mV:
                self.data["dV_enable_output_mV"] = dV_output_en_thrs_mV
                self.data["V_enable_output_threshold_mV"] = self.data[
                    "V_intermediate_enable_threshold_mV"
                ]
            else:
                self.data["dV_enable_output_mV"] = dV_output_imed_low_mV
                self.data["V_enable_output_threshold_mV"] = (
                    V_pre_output_mV + self.data["dV_enable_output_mV"]
                )

            if self.data["V_intermediate_disable_threshold_mV"] > V_pre_output_mV:
                self.data["V_disable_output_threshold_mV"] = self.data[
                    "V_intermediate_disable_threshold_mV"
                ]
            else:
                self.data["V_disable_output_threshold_mV"] = V_pre_output_mV

        else:
            self.data["dV_enable_output_mV"] = dV_output_en_thrs_mV
            self.data["V_enable_output_threshold_mV"] = self.data[
                "V_intermediate_enable_threshold_mV"
            ]
            self.data["V_disable_output_threshold_mV"] = self.data[
                "V_intermediate_disable_threshold_mV"
            ]

    def check_and_complete(self, verbose: bool = True) -> None:
        """
        checks virtual-source-settings for present values,
        adds default values to missing ones,
        checks against limits of algorithm
        """
        base_name = self.data.get(
            "converter_base",
            "neutral",
        )  # 2nd val = default if key missing

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
            self.check_and_complete(verbose=False)
            self._config_base = self.data
            self.data = config_stash
        else:
            raise NotImplementedError(
                f"[{self.name}] converter base '{base_name}' is unknown to system",
            )

        # General
        self._check_num("log_intermediate_voltage", 4.29e9, verbose=verbose)
        self._check_num("interval_startup_delay_drain_ms", 10000, verbose=verbose)

        self._check_num("V_input_max_mV", 10e3, verbose=verbose)
        self._check_num("I_input_max_mA", 4.29e3, verbose=verbose)
        self._check_num("V_input_drop_mV", 4.29e6, verbose=verbose)

        self._check_num("R_input_mOhm", 4.29e6, verbose=verbose)
        self.data["R_input_kOhm_n22"] = (
            (2**22) * self.data["R_input_mOhm"] / (10**6)
        )
        # TODO: possible optimization: n32 (range 1uOhm to 1 kOhm) is easier to calc in pru
        self._check_num("R_input_kOhm_n22", 4.29e9, verbose=verbose)

        self._check_num("C_intermediate_uF", 100e3, verbose=verbose)
        self._check_num("I_intermediate_leak_nA", 4.29e9, verbose=verbose)
        self._check_num("V_intermediate_init_mV", 10000, verbose=verbose)

        self._check_num("V_pwr_good_enable_threshold_mV", 10000, verbose=verbose)
        self._check_num("V_pwr_good_disable_threshold_mV", 10000, verbose=verbose)
        self._check_num("immediate_pwr_good_signal", 4.29e9, verbose=verbose)

        self._check_num("C_output_uF", 4.29e6, verbose=verbose)

        self._check_num("V_output_log_gpio_threshold_mV", 4.29e6, verbose=verbose)

        if "harvester" not in self.data and "harvester" in self._config_base:
            self.data["harvester"] = self._config_base["harvester"]

        # Boost-Converter
        self._check_num("enable_boost", 4.29e9, verbose=verbose)
        self._check_num("V_input_boost_threshold_mV", 10000, verbose=verbose)
        self._check_num("V_intermediate_max_mV", 10000, verbose=verbose)

        self._check_list("LUT_input_efficiency", 1.0, verbose=verbose)
        self._check_num("LUT_input_V_min_log2_uV", 20, verbose=verbose)
        # TODO: naming could confuse
        self._check_num("LUT_input_I_min_log2_nA", 20, verbose=verbose)

        # Buck-Converter
        self._check_num("enable_buck", 4.29e9, verbose=verbose)
        self._check_num("V_output_mV", 5000, verbose=verbose)
        self._check_num("V_buck_drop_mV", 5000, verbose=verbose)

        self._check_num("V_intermediate_enable_threshold_mV", 10000, verbose=verbose)
        self._check_num("V_intermediate_disable_threshold_mV", 10000, verbose=verbose)
        self._check_num("interval_check_thresholds_ms", 4.29e3, verbose=verbose)

        self._check_list("LUT_output_efficiency", 1.0, verbose=verbose)
        self._check_num("LUT_output_I_min_log2_nA", 20, verbose=verbose)

        # internal / derived parameters
        self.calculate_internal_states()
        self._check_num("dV_enable_output_mV", 4.29e6, verbose=verbose)
        self._check_num("V_enable_output_threshold_mV", 4.29e6, verbose=verbose)
        self._check_num("V_disable_output_threshold_mV", 4.29e6, verbose=verbose)
        self._check_num("Constant_us_per_nF_n28", 4.29e9, verbose=verbose)

    def _check_num(
        self,
        setting_key: str,
        max_value: Optional[float] = None,
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
        if not isinstance(set_value, (int, float)) or (set_value < 0):
            raise NotImplementedError(
                f"[{self.name}] '{setting_key}' must a single positive number, "
                f"but is '{set_value}'",
            )
        if set_value < 0:
            raise NotImplementedError(
                f"[{self.name}] {setting_key} = {set_value}, but must be >= 0",
            )
        if (max_value is not None) and (set_value > max_value):
            raise NotImplementedError(
                f"[{self.name}] {setting_key} = {set_value}, but must be <= {max_value}",
            )
        self.data[setting_key] = set_value

    def _check_list(
        self,
        setting_key: str,
        max_value: float = 1023,
        verbose: bool = True,
    ) -> None:
        default = flatten_list(self._config_base[setting_key])
        try:
            values = flatten_list(self.data[setting_key])
        except KeyError:
            values = default
            if verbose:
                logger.debug(
                    "Param '%s' not provided, set to inherited value = %s",
                    setting_key,
                    values[0],
                )
        if (
            (len(values) != len(default))
            or (min(values) < 0)
            or (max(values) > max_value)
        ):
            raise NotImplementedError(
                f"[{self.name}] {setting_key} must a list of {len(default)} values, "
                f"within range of [{0}; {max_value}]",
            )
        self.data[setting_key] = values

    def get_state_log_intermediate(self):
        return self.data["log_intermediate_voltage"] > 0

    def get_harvester(self) -> str:
        return self.data["harvester"]


T_vSrc = TypeVar("T_vSrc", VirtualSourceConfig, dict, str, Path)
