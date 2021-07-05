from typing import NoReturn
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
    vss: dict = None

    def __init__(self, vs_settings: dict = None):
        """ Container for VS Settings, Data will be checked and completed

        Args:
            vs_settings: if omitted, the data is generated from default values
        """
        # TODO: also handle preconfigured virtsources here, switch by name for now
        if isinstance(vs_settings, str) and Path(vs_settings).exists():
            vs_settings = Path(vs_settings)
        if isinstance(vs_settings, Path) and vs_settings.exists():
            with open(vs_settings, "r") as config_data:
                vs_settings = yaml.safe_load(config_data)["virtsource"]
        if isinstance(vs_settings, str) and vs_settings.strip().lower() == "bq25570":
            raise NotImplementedError(f"VirtualSource was set to {vs_settings}, but it isn't implemented yet")
        if isinstance(vs_settings, str) and vs_settings.strip().lower() == "bq25504":
            raise NotImplementedError(f"VirtualSource was set to {vs_settings}, but it isn't implemented yet")
        if isinstance(vs_settings, str) and vs_settings.strip().lower() == "default":
            vs_settings = None  # TODO: replace by real default

        if vs_settings is None:
            self.vss = dict()
        elif isinstance(vs_settings, VirtualSourceData):
            self.vss = vs_settings.vss
        elif isinstance(vs_settings, dict):
            self.vss = vs_settings
        else:
            raise NotImplementedError(
                f"VirtualSourceData was instantiated with '{vs_settings}' of type '{type(vs_settings)}', can't be handled")
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

        vs_list.append(int(self.vss["converter_mode"]))

        vs_list.append(int(self.vss["C_output_uF"] * 1e3))  # nF

        vs_list.append(int(self.vss["V_input_boost_threshold_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["C_storage_uF"] * 1e3))  # nF
        vs_list.append(int(self.vss["V_storage_init_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["V_storage_max_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["I_storage_leak_nA"] * 1))  # nA

        vs_list.append(int(self.vss["V_storage_enable_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["V_storage_disable_threshold_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["interval_check_thresholds_ms"] * 1e6))  # ns

        vs_list.append(int(self.vss["V_pwr_good_disable_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["V_pwr_good_enable_threshold_mV"] * 1e3))  # uV
        vs_list.append(int(self.vss["immediate_pwr_good_signal"]))  # bool

        vs_list.append(int(self.vss["dV_store_en_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["V_output_mV"] * 1e3))  # uV

        vs_list.append(int(self.vss["dV_store_low_mV"] * 1e3))  # uV

        # reduce resolution from n10 to n8 to fit in container
        vs_list.append([int(value / (2 ** 2)) for value in self.vss["LUT_input_efficiency_n10"]])

        # is now n4 -> resulting value for PRU is inverted, so 2^14 / value
        vs_list.append(
            [int((2 ** (4+10)) / value) if (value > 0) else (2 ** (4+10)) for value in self.vss["LUT_output_efficiency_n10"]])
        return vs_list

    def add_enable_voltage_drop(self) -> NoReturn:
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

        # first case: storage cap outside of en/dis-thresholds
        v_old = self.vss["V_storage_enable_threshold_mV"]
        if 1:  # TODO: this is boost-buck case, boost-only has v_out = v_old
            v_out = self.vss["V_output_mV"]
        else:
            v_out = v_old
        c_store = self.vss["C_storage_uF"]
        c_out = self.vss["C_output_uF"]
        self.vss["dV_store_en_mV"] = v_old - pow(pow(v_old, 2) - (c_out / c_store) * pow(v_out, 2), 0.5)

        # second case: storage cap below v_out (only different for enabled buck), enable when >= v_out
        # v_enable is either bucks v_out or same dV-Value is calculated a second time
        self.vss["dV_store_low_mV"] = v_out * (1 - pow(1 - c_out / c_store, 0.5))

    def check_and_complete(self) -> NoReturn:
        """ checks virtual-source-settings for present values, adds default values to missing ones, checks limits
        TODO: fill with values from real BQ-IC
        """
        self._check_num("converter_mode", 100, 4e9)

        self._check_num("C_output_uF", 1, 4e6)

        self._check_num("V_input_boost_threshold_mV", 130, 5000)

        self._check_num("C_storage_uF", 1000, 4e6)
        self._check_num("V_storage_init_mV", 3500, 10000)
        self._check_num("V_storage_max_mV", 4200, 10000)
        self._check_num("I_storage_leak_nA", 10, 4e9)

        self._check_num("V_storage_enable_threshold_mV", 3000, 5000)
        self._check_num("V_storage_disable_threshold_mV", 2300, 5000)

        self._check_num("interval_check_thresholds_ms", 65, 4e3)

        self._check_num("V_pwr_good_disable_threshold_mV", 2400, 5000)
        self._check_num("V_pwr_good_enable_threshold_mV", 3000, 5000)
        self._check_num("immediate_pwr_good_signal", 0, 1)

        self._check_num("V_output_mV", 2300, 5000)

        self.add_enable_voltage_drop()
        self._check_num("dV_store_en_mV", 0, 4e6)
        self._check_num("dV_store_low_mV", 0, 4e6)

        # Look up tables, TODO: test if order in PRU-2d-array is maintained,
        self._check_list("LUT_input_efficiency_n10", 12 * [12 * [512]], 1023)
        self._check_list("LUT_output_efficiency_n10", 12 * [819], 1023)

    def _check_num(self, setting_key: str, default: float, max_value: float = None) -> NoReturn:
        try:
            set_value = self.vss[setting_key]
        except KeyError:
            set_value = default
            logger.debug(f"[virtSource] Setting '{setting_key}' was not provided, will be set to default = {default}")
        if not isinstance(set_value, (int, float)) or (set_value < 0):
            raise NotImplementedError(
                f"[virtSource] '{setting_key}' must a single positive number, but is '{set_value}'")
        if (max_value is not None) and (set_value > max_value):
            raise NotImplementedError(f"[virtSource] {setting_key} = {set_value} must be smaller than {max_value}")
        self.vss[setting_key] = set_value

    def _check_list(self, settings_key: str, default: list, max_value: float = 1023) -> NoReturn:
        default = flatten_dict_list(default)
        try:
            values = flatten_dict_list(self.vss[settings_key])
        except KeyError:
            values = default
            logger.debug(f"[virtSource] Setting {settings_key} was not provided, will be set to default = {values[0]}")
        if (len(values) != len(default)) or (min(values) < 0) or (max(values) > max_value):
            raise NotImplementedError(
                f"{settings_key} must a list of {len(default)} values, within range of [0; {max_value}]")
        self.vss[settings_key] = values
