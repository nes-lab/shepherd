from typing import NoReturn, Union
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)


def flatten_dict_list(dl) -> list:
    """ small helper FN to convert (multi-dimensional) dicts or lists to 1D list

    Args:
        dl: (multi-dimensional) dicts or lists
    Returns:
        1D list
    """
    if len(dl) == 1:
        if isinstance(dl[0], list):
            result = flatten_dict_list(dl[0])
        else:
            result = dl
    elif isinstance(dl[0], list):
        result = flatten_dict_list(dl[0]) + flatten_dict_list(dl[1:])
    else:
        result = [dl[0]] + flatten_dict_list(dl[1:])
    return result


class VirtualSourceData(object):
    """
    Container for VS Settings, Data will be checked and completed
    - settings will be created from default values when omitted
    - internal settings are derived from existing values (PRU has no FPU, so it is done here)
    - settings can be exported in required format
    """
    _config: dict = {}
    _name: str = "vSource"
    _def_file = "virtual_source_defs.yml"

    def __init__(self,
                 setting: Union[dict, str, Path] = None,
                 log_intermediate_voltage: bool = None,
                 samplerate_sps: int = 100_000):
        """ Container for VS Settings, Data will be checked and completed

        Args:
            setting: if omitted, the data is generated from default values
        """
        self.samplerate_sps = samplerate_sps

        def_path = Path(__file__).parent.resolve()/self._def_file
        with open(def_path, "r") as def_data:
            self._config_defs = yaml.safe_load(def_data)["virtsources"]
            self._config_base = self._config_defs["neutral"]
        self._inheritance = []

        if isinstance(setting, str) and Path(setting).exists():
            setting = Path(setting)

        if isinstance(setting, Path) and setting.exists() and \
                setting.is_file() and setting.suffix in ["yaml", "yml"]:
            self._inheritance.append(str(setting))
            with open(setting, "r") as config_data:
                setting = yaml.safe_load(config_data)["virtsource"]
        if isinstance(setting, str):
            if setting in self._config_defs:
                self._inheritance.append(setting)
                setting = self._config_defs[setting]
            else:
                raise NotImplementedError(f"[{self._name}] was set to '{setting}', but definition missing in '{self._def_file}'")

        if setting is None:
            self._config = {}
        elif isinstance(setting, VirtualSourceData):
            self._inheritance.append(self._name + "-Element")
            self._config = setting._config
            self.samplerate_sps = setting.samplerate_sps
        elif isinstance(setting, dict):
            self._inheritance.append("parameter-dict")
            self._config = setting
        else:
            raise NotImplementedError(
                f"[{self._name}] {type(setting)}'{setting}' could not be handled. In case of file-path -> does it exist?")

        if log_intermediate_voltage is not None:
            self._config["log_intermediate_voltage"] = log_intermediate_voltage

        self.check_and_complete()
        logger.debug(f"[{self._name}] initialized with the following inheritance-chain: '{self._inheritance}'")

    def export_for_sysfs(self) -> list:
        """ prepares virtsource settings for PRU core (a lot of unit-conversions)

        The current emulator in PRU relies on the virtsource settings.
        This Fn add values in correct order and convert to requested unit

        Returns:
            int-list (2nd level for LUTs) that can be feed into sysFS
        """
        return [
            # General
            int(self._config["converter_mode"]),
            int(self._config["interval_startup_delay_drain_ms"] * self.samplerate_sps // 10 ** 3),  # n, samples
            int(self._config["V_input_max_mV"] * 1e3),  # uV
            int(self._config["I_input_max_mA"] * 1e6),  # nA
            int(self._config["V_input_drop_mV"] * 1e3),  # uV
            int(self._config["Constant_1k_per_Ohm"] * 1),  # 1/mOhm
            int(self._config["Constant_us_per_nF_n28"]),  # us/nF = us*V / nA*s
            int(self._config["V_intermediate_init_mV"] * 1e3),  # uV
            int(self._config["I_intermediate_leak_nA"] * 1),  # nA
            int(self._config["V_enable_output_threshold_mV"] * 1e3),  # uV
            int(self._config["V_disable_output_threshold_mV"] * 1e3),  # uV
            int(self._config["dV_enable_output_mV"] * 1e3),  # uV
            int(self._config["interval_check_thresholds_ms"] * self.samplerate_sps // 10 ** 3),  # n, samples
            int(self._config["V_pwr_good_enable_threshold_mV"] * 1e3),  # uV
            int(self._config["V_pwr_good_disable_threshold_mV"] * 1e3),  # uV
            int(self._config["immediate_pwr_good_signal"] > 0),  # bool
            int(self._config["V_output_log_gpio_threshold_mV"] * 1e3),  # uV
            # Boost
            int(self._config["V_input_boost_threshold_mV"] * 1e3),  # uV
            int(self._config["V_intermediate_max_mV"] * 1e3),  # uV
            # Buck
            int(self._config["V_output_mV"] * 1e3),  # uV
            int(self._config["V_buck_drop_mV"] * 1e3),  # uV
            # LUTs
            int(self._config["LUT_input_V_min_log2_uV"]),  #
            int(self._config["LUT_input_I_min_log2_nA"]),  #
            int(self._config["LUT_output_I_min_log2_nA"]),  #
            # reduce resolution to n8 to fit in container
            [min(255, int(256 * value)) if (value > 0) else 0 for value in self._config["LUT_input_efficiency"]],
            # is now n4 -> resulting value for PRU is inverted, so 2^4 / value, inv-max = 2^14 for min-value = 1/1024
            [min((2**14), int((2**4) / value)) if (value > 0) else int(2**14) for value in self._config["LUT_output_efficiency"]],
        ]

    def calculate_internal_states(self) -> NoReturn:
        """
        add the following internal variables:
        - converter_mode
        - Constant_us_per_nF_n28
        - dV_enable_output_mV
        - V_enable_output_threshold_mV
        - V_disable_output_threshold_mV
        """
        # assembles bitmask from discrete values
        self._config["converter_mode"] = 0
        enable_storage = self._config["C_intermediate_uF"] > 0
        self._config["converter_mode"] += 1 if enable_storage else 0
        enable_boost = self._config["enable_boost"] and enable_storage
        self._config["converter_mode"] += 2 if enable_boost else 0
        self._config["converter_mode"] += 4 if (self._config["enable_buck"] > 0) else 0
        self._config["converter_mode"] += 8 if (self._config["log_intermediate_voltage"] > 0) else 0

        # calc constant to convert capacitor-current to Voltage-delta
        # dV[uV] = constant[us/nF] * current[nA] = constant[us*V/nAs] * current[nA]
        C_storage_uF = max(self._config["C_intermediate_uF"], 0.001)
        self._config["Constant_us_per_nF_n28"] = (10 ** 3 * (2 ** 28)) // (C_storage_uF * self.samplerate_sps)

        # inverse resistance constant
        R_input_mOhm = max(self._config["R_input_mOhm"], 0.001)
        self._config["Constant_1k_per_Ohm"] = max(10 ** 6 / R_input_mOhm, 1)

        """
        compensate for (hard to detect) current-surge of real capacitors when converter gets turned on
        -> this can be const value, because the converter always turns on with "V_storage_enable_threshold_uV"
        TODO: currently neglecting: delay after disabling converter, boost only has simpler formula, second enabling when V_Cap >= V_out

        Math behind this calculation:
        Energy-Change Storage Cap   ->  E_new = E_old - E_output
        with Energy of a Cap 	    -> 	E_x = C_x * V_x^2 / 2
        combine formulas 		    -> 	C_store * V_store_new^2 / 2 = C_store * V_store_old^2 / 2 - C_out * V_out^2 / 2
        convert formula to V_new 	->	V_store_new^2 = V_store_old^2 - (C_out / C_store) * V_out^2
        convert into dV	 	        ->	dV = V_store_new - V_store_old
        in case of V_cap = V_out 	-> 	dV = V_store_old * (sqrt(1 - C_out / C_store) - 1)
        -> dV values will be reversed (negated), because dV is always negative (Voltage drop)
        """
        v_old = self._config["V_intermediate_enable_threshold_mV"]
        v_out = self._config["V_output_mV"]
        c_store = self._config["C_intermediate_uF"]
        c_out = self._config["C_output_uF"]
        if c_store > 0 and c_out > 0:
            # first case: storage cap outside of en/dis-thresholds
            dV_output_en_thrs_mV = v_old - pow(pow(v_old, 2) - (c_out / c_store) * pow(v_out, 2), 0.5)

            # second case: storage cap below v_out (only different for enabled buck), enable when >= v_out
            # v_enable is either bucks v_out or same dV-Value is calculated a second time
            dV_output_imed_low_mV = v_out * (1 - pow(1 - c_out / c_store, 0.5))
        else:
            dV_output_en_thrs_mV = 0
            dV_output_imed_low_mV = 0

        # protect from complex solutions (non valid input combinations)
        if not (isinstance(dV_output_en_thrs_mV, (int, float)) and (dV_output_en_thrs_mV >= 0)):
            dV_output_en_thrs_mV = 0
        if not (isinstance(dV_output_imed_low_mV, (int, float)) and (dV_output_imed_low_mV >= 0)):
            dV_output_imed_low_mV = 0

        # decide which hysteresis-thresholds to use for buck-regulator
        if self._config["enable_buck"] > 0:
            V_pre_output_mV = self._config["V_output_mV"] + self._config["V_buck_drop_mV"]

            if self._config["V_intermediate_enable_threshold_mV"] > V_pre_output_mV:
                self._config["dV_enable_output_mV"] = dV_output_en_thrs_mV
                self._config["V_enable_output_threshold_mV"] = self._config["V_intermediate_enable_threshold_mV"]
            else:
                self._config["dV_enable_output_mV"] = dV_output_imed_low_mV
                self._config["V_enable_output_threshold_mV"] = V_pre_output_mV + self._config["dV_enable_output_mV"]

            if self._config["V_intermediate_disable_threshold_mV"] > V_pre_output_mV:
                self._config["V_disable_output_threshold_mV"] = self._config["V_intermediate_disable_threshold_mV"]
            else:
                self._config["V_disable_output_threshold_mV"] = V_pre_output_mV

        else:
            self._config["dV_enable_output_mV"] = dV_output_en_thrs_mV
            self._config["V_enable_output_threshold_mV"] = self._config["V_intermediate_enable_threshold_mV"]
            self._config["V_disable_output_threshold_mV"] = self._config["V_intermediate_disable_threshold_mV"]

    def check_and_complete(self, verbose: bool = True) -> NoReturn:
        """ checks virtual-source-settings for present values, adds default values to missing ones, checks against limits of algorithm
        """
        if "converter_base" in self._config:
            base_name = self._config["converter_base"]
        else:
            base_name = "neutral"

        if base_name in self._inheritance:
            raise ValueError(
                f"[{self._name}] loop detected in 'base'-inheritance-system @ '{base_name}' already in {self._inheritance}")
        else:
            self._inheritance.append(base_name)

        if base_name == "neutral":
            # root of recursive completion
            self._config_base = self._config_defs[base_name]
            logger.debug(f"[{self._name}] Parameter-Set will be completed with '{base_name}'-base")
            verbose = False
        elif base_name in self._config_defs:
            config_stash = self._config
            self._config = self._config_defs[base_name]
            logger.debug(f"[{self._name}] Parameter-Set will be completed with '{base_name}'-base")
            self.check_and_complete(verbose=False)
            self._config_base = self._config
            self._config = config_stash
        else:
            raise NotImplementedError(f"[{self._name}] converter base '{base_name}' is unknown to system")

        # General
        self._check_num("log_intermediate_voltage", 4.29e9, verbose=verbose)
        self._check_num("interval_startup_delay_drain_ms", 10000, verbose=verbose)

        self._check_num("V_input_max_mV", 10e3, verbose=verbose)
        self._check_num("I_input_max_mA", 4.29e3, verbose=verbose)
        self._check_num("V_input_drop_mV", 4.29e6, verbose=verbose)
        self._check_num("R_input_mOhm", 4.29e6, verbose=verbose)

        self._check_num("C_intermediate_uF", 100e3, verbose=verbose)
        self._check_num("I_intermediate_leak_nA", 4.29e9, verbose=verbose)
        self._check_num("V_intermediate_init_mV", 10000, verbose=verbose)

        self._check_num("V_pwr_good_enable_threshold_mV", 10000, verbose=verbose)
        self._check_num("V_pwr_good_disable_threshold_mV", 10000, verbose=verbose)
        self._check_num("immediate_pwr_good_signal", 4.29e9, verbose=verbose)

        self._check_num("C_output_uF", 4.29e6, verbose=verbose)

        self._check_num("V_output_log_gpio_threshold_mV", 4.29e6, verbose=verbose)

        # Boost
        self._check_num("enable_boost", 4.29e9, verbose=verbose)
        self._check_num("V_input_boost_threshold_mV", 10000, verbose=verbose)
        self._check_num("V_intermediate_max_mV", 10000, verbose=verbose)

        self._check_list("LUT_input_efficiency", 1.0, verbose=verbose)
        self._check_num("LUT_input_V_min_log2_uV", 20, verbose=verbose)  # TODO: naming could confuse
        self._check_num("LUT_input_I_min_log2_nA", 20, verbose=verbose)

        # Buck
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
        self._check_num("Constant_1k_per_Ohm", 4.29e9, verbose=verbose)

    def _check_num(self, setting_key: str, max_value: float = None, verbose: bool = True) -> NoReturn:
        try:
            set_value = self._config[setting_key]
        except KeyError:
            set_value = self._config_base[setting_key]
            if verbose:
                logger.debug(f"[{self._name}] '{setting_key}' not provided, set to inherited value = {set_value}")
        if not isinstance(set_value, (int, float)) or (set_value < 0):
            raise NotImplementedError(
                f"[{self._name}] '{setting_key}' must a single positive number, but is '{set_value}'")
        if set_value < 0:
            raise NotImplementedError(f"[{self._name}] {setting_key} = {set_value}, but must be >= 0")
        if (max_value is not None) and (set_value > max_value):
            raise NotImplementedError(f"[{self._name}] {setting_key} = {set_value}, but must be <= {max_value}")
        self._config[setting_key] = set_value

    def _check_list(self, setting_key: str, max_value: float = 1023, verbose: bool = True) -> NoReturn:
        default = flatten_dict_list(self._config_base[setting_key])
        try:
            values = flatten_dict_list(self._config[setting_key])
        except KeyError:
            values = default
            if verbose:
                logger.debug(f"[{self._name}] '{setting_key}' not provided, will be set to inherited value = {values[0]}")
        if (len(values) != len(default)) or (min(values) < 0) or (max(values) > max_value):
            raise NotImplementedError(
                f"[{self._name}] {setting_key} must a list of {len(default)} values, within range of [{0}; {max_value}]")
        self._config[setting_key] = values

    def get_state_log_intermediate(self):
        return self._config["log_intermediate_voltage"] > 0
