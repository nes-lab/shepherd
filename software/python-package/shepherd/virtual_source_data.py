from typing import NoReturn
from pathlib import Path
import yaml
import logging

from shepherd.commons import SAMPLE_INTERVAL_US

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
    vss: dict = None

    def __init__(self, vs_settings: dict = None):
        """ Container for VS Settings, Data will be checked and completed

        Args:
            vs_settings: if omitted, the data is generated from default values
        """
        vs_defs = Path("./virtual_source_defs.yml")
        with open(vs_defs, "r") as def_data:
            self.vs_defines = yaml.safe_load(def_data)["virtsources"]
        self.vs_inheritance = list()

        if isinstance(vs_settings, str) and Path(vs_settings).exists():
            vs_settings = Path(vs_settings)
        if isinstance(vs_settings, Path) and vs_settings.exists():
            with open(vs_settings, "r") as config_data:
                vs_settings = yaml.safe_load(config_data)["virtsource"]
        if isinstance(vs_settings, str):
            if vs_settings in self.vs_defines:
                self.vs_inheritance.append(vs_settings)
                vs_settings = self.vs_defines[vs_settings]
            else:
                raise NotImplementedError(f"VirtualSource was set to '{vs_settings}', but definition missing in 'virtual_source_defs.yml'")

        if vs_settings is None:
            self.vss = dict()
        elif isinstance(vs_settings, VirtualSourceData):
            self.vss = vs_settings.vss
        elif isinstance(vs_settings, dict):
            self.vss = vs_settings
        else:
            raise NotImplementedError(
                f"VirtualSourceData {type(vs_settings)}'{vs_settings}' could not be handled. In case of file-path -> does it exist?")
        self.check_and_complete()

    def get_as_dict(self) -> dict:
        """ offers a checked and completed version of the settings

        Returns:
            internal settings container
        """
        return self.vss

    def get_as_list(self) -> list:
        """ multi-level dict is flattened, good for testing

        Returns:
            1D-Content
        """
        return flatten_dict_list(self.vss)

    def export_for_sysfs(self) -> list:
        """ prepares virtsource settings for PRU core (a lot of unit-conversions)

        The current emulator in PRU relies on the virtsource settings.
        This Fn add values in correct order and convert to requested unit

        Returns:
            int-list (2nd level for LUTs) that can be feed into sysFS
        """
        vs_list = list([])

        # General
        vs_list.append(int(self.vss["converter_mode"]))
        vs_list.append(int(self.vss["interval_startup_delay_drain_ms"] * 1e3 / SAMPLE_INTERVAL_US))  # n, samples

        vs_list.append(int(self.vss["V_input_max_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["I_input_max_mA"] * 1e6))  # nA
        vs_list.append(int(self.vss["V_input_drop_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["Constant_us_per_nF_n28"]))  # us/nF = us*V / nA*s
        vs_list.append(int(self.vss["V_intermediate_init_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["I_intermediate_leak_nA"] * 1))  # nA

        vs_list.append(int(self.vss["V_enable_output_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["V_disable_output_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["dV_enable_output_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["interval_check_thresholds_ms"] * 1e3 / SAMPLE_INTERVAL_US))  # n, samples

        vs_list.append(int(self.vss["V_pwr_good_enable_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["V_pwr_good_disable_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["immediate_pwr_good_signal"] > 0))  # bool

        # Boost
        vs_list.append(int(self.vss["V_input_boost_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["V_intermediate_max_mV"] * 1e3))  # uV

        # Buck
        vs_list.append(int(self.vss["V_output_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["V_buck_drop_mV"] * 1e3))  # uV

        # LUTs
        vs_list.append(int(self.vss["LUT_input_V_min_log2_uV"]))  #
        vs_list.append(int(self.vss["LUT_input_I_min_log2_nA"]))  #
        vs_list.append(int(self.vss["LUT_output_I_min_log2_nA"]))  #

        # reduce resolution to n8 to fit in container
        vs_list.append([min(255, int(256 * value)) if (value > 0) else 0 for value in self.vss["LUT_input_efficiency"]])

        # is now n4 -> resulting value for PRU is inverted, so 2^4 / value, inv-max = 2^14 for min-value = 1/1024
        vs_list.append([min((2**14), int((2**4) / value)) if (value > 0) else int(2**14) for value in self.vss["LUT_output_efficiency"]])
        return vs_list

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
        self.vss["converter_mode"] = 0
        enable_storage = self.vss["C_intermediate_uF"] > 0
        self.vss["converter_mode"] += 1 if enable_storage else 0
        enable_boost = self.vss["enable_boost"] and enable_storage
        self.vss["converter_mode"] += 2 if enable_boost else 0
        self.vss["converter_mode"] += 4 if (self.vss["enable_buck"] > 0) else 0
        self.vss["converter_mode"] += 8 if (self.vss["log_intermediate_voltage"] > 0) else 0

        # calc constant to convert capacitor-current to Voltage-delta
        # dV[uV] = constant[us/nF] * current[nA] = constant[us*V/nAs] * current[nA]
        C_storage_uF = max(self.vss["C_intermediate_uF"], 0.001)
        self.vss["Constant_us_per_nF_n28"] = (SAMPLE_INTERVAL_US * (2**28)) / (1000 * C_storage_uF)

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
        v_old = self.vss["V_intermediate_enable_threshold_mV"]
        v_out = self.vss["V_output_mV"]
        c_store = self.vss["C_intermediate_uF"]
        c_out = self.vss["C_output_uF"]
        if c_store > 0 and c_out > 0:
            # first case: storage cap outside of en/dis-thresholds
            dV_output_en_thrs_mV = v_old - pow(pow(v_old, 2) - (c_out / c_store) * pow(v_out, 2), 0.5)

            # second case: storage cap below v_out (only different for enabled buck), enable when >= v_out
            # v_enable is either bucks v_out or same dV-Value is calculated a second time
            dV_output_imed_low_mV = v_out * (1 - pow(1 - c_out / c_store, 0.5))
        else:
            dV_output_en_thrs_mV = 0
            dV_output_imed_low_mV = 0

        # decide which hysteresis-thresholds to use for buck-regulator
        if self.vss["enable_buck"] > 0:
            V_pre_output_mV = self.vss["V_output_mV"] + self.vss["V_buck_drop_mV"]

            if self.vss["V_intermediate_enable_threshold_mV"] > V_pre_output_mV:
                self.vss["dV_enable_output_mV"] = dV_output_en_thrs_mV
                self.vss["V_enable_output_threshold_mV"] = self.vss["V_intermediate_enable_threshold_mV"]
            else:
                self.vss["dV_enable_output_mV"] = dV_output_imed_low_mV
                self.vss["V_enable_output_threshold_mV"] = V_pre_output_mV + self.vss["dV_output_enable_mV"]

            if self.vss["V_intermediate_disable_threshold_mV"] > V_pre_output_mV:
                self.vss["V_disable_output_threshold_mV"] = self.vss["V_intermediate_disable_threshold_mV"]
            else:
                self.vss["V_disable_output_threshold_mV"] = V_pre_output_mV

        else:
            self.vss["dV_enable_output_mV"] = dV_output_en_thrs_mV
            self.vss["V_enable_output_threshold_mV"] = self.vss["V_intermediate_enable_threshold_mV"]
            self.vss["V_disable_output_threshold_mV"] = self.vss["V_intermediate_disable_threshold_mV"]

    def check_and_complete(self, debug: bool = True) -> NoReturn:
        """ checks virtual-source-settings for present values, adds default values to missing ones, checks limits
        """
        if "converter_base" in self.vss:
            base_name = self.vss["converter_base"]
        else:
            base_name = "neutral"

        if base_name in self.vs_inheritance:
            raise ValueError(f"[virtSource] loop detected in 'converter_base'-inheritance-system @ last entry of {self.vs_inheritance}")
        else:
            self.vs_inheritance.append(base_name)

        if base_name == "neutral":
            # root of recursive completion
            self.vss_base = self.vs_defines[base_name]
        elif base_name in self.vs_defines:
            vss_stash = self.vss
            self.vss = self.vs_defines[base_name]
            self.check_and_complete(debug=False)
            logger.debug(f"[virtSource] config set was completed with '{base_name}'-base")
            self.vss_base = self.vss
            self.vss = vss_stash
        else:
            raise NotImplementedError(f"[virtSource] converter base '{base_name}' is unknown to system")

        # General
        self._check_num("log_intermediate_voltage", 4.29e9)
        self._check_num("interval_startup_delay_drain_ms", 10000)

        self._check_num("V_input_max_mV", 10e3)
        self._check_num("I_input_max_mA", 4.29e3)
        self._check_num("V_input_drop_mV", 4.29e6)

        self._check_num("C_intermediate_uF", 100e3)
        self._check_num("I_intermediate_leak_nA", 4.29e9)
        self._check_num("V_intermediate_init_mV", 10000)

        self._check_num("V_pwr_good_enable_threshold_mV", 10000)
        self._check_num("V_pwr_good_disable_threshold_mV", 10000)
        self._check_num("immediate_pwr_good_signal", 4.29e9)

        self._check_num("C_output_uF", 4.29e6)

        # Boost
        self._check_num("enable_boost", 4.29e9)
        self._check_num("V_input_boost_threshold_mV", 10000)
        self._check_num("V_intermediate_max_mV", 10000)

        self._check_list("LUT_input_efficiency", 1.0)
        self._check_num("LUT_input_V_min_log2_uV", 20)  # TODO: naming could confuse
        self._check_num("LUT_input_I_min_log2_nA", 20)

        # Buck
        self._check_num("enable_buck", 4.29e9)
        self._check_num("V_output_mV", 5000)
        self._check_num("V_buck_drop_mV", 5000)

        self._check_num("V_intermediate_enable_threshold_mV", 10000)
        self._check_num("V_intermediate_disable_threshold_mV", 10000)
        self._check_num("interval_check_thresholds_ms", 4.29e3)

        self._check_list("LUT_output_efficiency", 1.0)
        self._check_num("LUT_output_I_min_log2_nA", 20)

        # internal
        self.calculate_internal_states()
        self._check_num("dV_enable_output_mV", 4.29e6)
        self._check_num("V_enable_output_threshold_mV", 4.29e6)
        self._check_num("V_disable_output_threshold_mV", 4.29e6)
        self._check_num("Constant_us_per_nF_n28", 4.29e9)

    def _check_num(self, setting_key: str, max_value: float = None) -> NoReturn:
        try:
            set_value = self.vss[setting_key]
        except KeyError:
            set_value = self.vss_base[setting_key]
            logger.debug(f"[virtSource] Setting '{setting_key}' was not provided, will be set to default = {set_value}")
        if not isinstance(set_value, (int, float)) or (set_value < 0):
            raise NotImplementedError(
                f"[virtSource] '{setting_key}' must a single positive number, but is '{set_value}'")
        if set_value < 0:
            raise NotImplementedError(f"[virtSource] {setting_key} = {set_value} must be >= 0")
        if (max_value is not None) and (set_value > max_value):
            raise NotImplementedError(f"[virtSource] {setting_key} = {set_value} must be <= {max_value}")
        self.vss[setting_key] = set_value

    def _check_list(self, setting_key: str, max_value: float = 1023) -> NoReturn:
        default = flatten_dict_list(self.vss_base[setting_key])
        try:
            values = flatten_dict_list(self.vss[setting_key])
        except KeyError:
            values = default
            logger.debug(f"[virtSource] Setting {setting_key} was not provided, will be set to default = {values[0]}")
        if (len(values) != len(default)) or (min(values) < 0) or (max(values) > max_value):
            raise NotImplementedError(
                f"[virtSource] {setting_key} must a list of {len(default)} values, within range of [{0}; {max_value}]")
        self.vss[setting_key] = values

    def get_state_log_intermediate(self):
        return self.vss["log_intermediate_voltage"] > 0
