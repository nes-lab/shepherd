from typing import NoReturn
from shepherd import VirtualSourceData, CalibrationData
import math

# NOTE: DO NOT OPTIMIZE -> stay close to original code-base

class VirtualSource(object):
    """
    this is ported py-version of the pru-code, goals:
    - stay close to original code-base
    - offer a comparison for the tests
    - step 1 to a virtualization of emulation

    """

    vsc = dict()
    cal = CalibrationData.from_default()

    def __init__(self, vs_settings, cal_setting):
        """

        :param vs_settings: YAML-Path, dict, or regulator-name
        """
        if cal_setting is not None:
            self.cal = cal_setting

        # NOTE:
        #  - yaml is based on nA, mV, ms, uF
        #  - c-code and py-copy is using nA, uV, ns, nF, fW
        vs_settings = VirtualSourceData(vs_settings)
        values = vs_settings.export_for_sysfs()

        # generate a new dict from raw_list (that is intended for PRU / sys_fs, see commons.h)
        LUT_SIZE = 12
        self.vsc["LUT_size"] = LUT_SIZE

        # General Reg Config
        self.vsc["converter_mode"] = values[0]
        self.vsc["interval_startup_disabled_drain_n"] = values[1]

        self.vsc["V_input_max_uV"] = values[2]
        self.vsc["I_input_max_nA"] = values[3]
        self.vsc["V_input_drop_uV"] = values[4]
        self.vsc["Constant_1k_per_Ohm"] = values[5]

        self.vsc["Constant_us_per_nF"] = values[6] / (2**28)
        self.vsc["V_intermediate_init_uV"] = values[7]  # allow a proper / fast startup
        self.vsc["I_intermediate_leak_nA"] = values[8]

        self.vsc["V_enable_output_threshold_uV"] = values[9]  # -> target gets connected (hysteresis-combo with next value)
        self.vsc["V_disable_output_threshold_uV"] = values[10]  # -> target gets disconnected
        self.vsc["dV_enable_output_uV"] = values[11]
        self.vsc["interval_check_thresholds_n"] = values[12]  # some BQs check every 65 ms if output should be disconnected

        self.vsc["V_pwr_good_enable_threshold_uV"] = values[13]  # range where target is informed by output-pin
        self.vsc["V_pwr_good_disable_threshold_uV"] = values[14]
        self.vsc["immediate_pwr_good_signal"] = values[15]

        self.vsc["V_output_log_gpio_threshold_uV"] = values[16]

        # boost regulator
        self.vsc["V_input_boost_threshold_uV"] = values[17]  # min input-voltage for the boost converter to work
        self.vsc["V_intermediate_max_uV"] = values[18]  # -> boost shuts off

        # Buck Boost, ie. BQ25570)
        self.vsc["V_output_uV"] = values[19]
        self.vsc["V_buck_drop_uV"] = values[20]

        # LUTs
        self.vsc["LUT_input_V_min_log2_uV"] = values[21]
        self.vsc["LUT_input_I_min_log2_nA"] = values[22]
        self.vsc["LUT_output_I_min_log2_nA"] = values[23]
        self.vsc["LUT_inp_efficiency_n8"] = values[24]  # depending on inp_voltage, inp_current, (cap voltage),
        self.vsc["LUT_out_inv_efficiency_n4"] = values[25]  # depending on output_current

        # boost internal state
        self.vsc["V_input_uV"] = 0.0
        self.vsc["P_inp_fW"] = 0.0
        self.vsc["P_out_fW"] = 0.0

        # container for the stored energy
        self.vsc["V_mid_uV"] = self.vsc["V_intermediate_init_uV"]

        # buck internal state
        self.vsc["enable_storage"] = (int(self.vsc["converter_mode"]) & 0b0001) > 0
        self.vsc["enable_boost"] = (int(self.vsc["converter_mode"]) & 0b0010) > 0
        self.vsc["enable_buck"] = (int(self.vsc["converter_mode"]) & 0b0100) > 0
        self.vsc["enable_log_mid"] = (int(self.vsc["converter_mode"]) & 0b1000) > 0

        self.vsc["V_out_dac_uV"] = self.vsc["V_output_uV"]
        self.vsc["V_out_dac_raw"] = self.conv_uV_to_dac_raw(self.vsc["V_out_dac_uV"])
        self.vsc["power_good"] = True

        # prepare hysteresis-thresholds
        if self.vsc["dV_enable_output_uV"] > self.vsc["V_enable_output_threshold_uV"]:
            self.vsc["V_enable_output_threshold_uV"] = self.vsc["dV_enable_output_uV"]

        # pulled from update_states_and_output() due to easier static init
        self.vsc["sample_count"] = 0xFFFFFFF0
        self.vsc["is_outputting"] = True

        self.vsc["vsource_skip_gpio_logging"] = False

        # TEST-SIMPLIFICATION - code below is not part of pru-code
        self.P_in_fW: float = 0
        self.P_out_fW: float = 0

    def calc_inp_power(self, input_voltage_uV: int, input_current_nA: int) -> int:
        if input_voltage_uV < 0:
            input_voltage_uV = 0
        if input_current_nA < 0:
            input_current_nA = 0

        if input_voltage_uV > self.vsc["V_input_drop_uV"]:
            input_voltage_uV -= self.vsc["V_input_drop_uV"]
        else:
            input_voltage_uV = 0

        if input_voltage_uV > self.vsc["V_input_max_uV"]:
            input_voltage_uV = self.vsc["V_input_max_uV"]

        if input_current_nA > self.vsc["I_input_max_nA"]:
            input_current_nA = self.vsc["I_input_max_nA"]

        self.vsc["V_input_uV"] = input_voltage_uV

        if self.vsc["enable_boost"]:
            if input_voltage_uV < self.vsc["V_input_boost_threshold_uV"]:
                input_voltage_uV = 0
            if input_voltage_uV > self.vsc["V_mid_uV"]:
                input_voltage_uV = self.vsc["V_mid_uV"]
        elif not self.vsc["enable_storage"]:
            # direct connection
            self.vsc["V_mid_uV"] = input_voltage_uV
            input_voltage_uV = 0
        else:
            if input_voltage_uV > self.vsc["V_mid_uV"]:
                I_max_nA = (input_voltage_uV - self.vsc["V_mid_uV"]) * self.vsc["Constant_1k_per_Ohm"]
                if input_current_nA > I_max_nA:
                    input_current_nA = I_max_nA
                input_voltage_uV = self.vsc["V_mid_uV"]
            else:
                input_voltage_uV = 0

        if self.vsc["enable_boost"]:
            eta_inp = self.get_input_efficiency(input_voltage_uV, input_current_nA)
        else:
            eta_inp = 1.0

        self.vsc["P_inp_fW"] = input_voltage_uV * input_current_nA * eta_inp
        return round(self.vsc["P_inp_fW"])  # return NOT original, added for easier testing

    def calc_out_power(self, current_adc_raw: int) -> int:
        if current_adc_raw < 0:
            current_adc_raw = 0
        elif current_adc_raw >= (2 ** 18):
            current_adc_raw = (2 ** 18) - 1

        P_leak_fW = self.vsc["V_mid_uV"] * self.vsc["I_intermediate_leak_nA"]
        I_out_nA = self.conv_adc_raw_to_nA(current_adc_raw)
        if self.vsc["enable_buck"]:
            eta_inv_out = self.get_output_inv_efficiency(I_out_nA)
        else:
            eta_inv_out = 1.0

        self.vsc["P_out_fW"] = I_out_nA * self.vsc["V_out_dac_uV"] * eta_inv_out + P_leak_fW

        if self.vsc["interval_startup_disabled_drain_n"] > 0:
            self.vsc["interval_startup_disabled_drain_n"] -= 1
            self.vsc["P_out_fW"] = 0

        return round(self.vsc["P_out_fW"])  # return NOT original, added for easier testing

    def update_cap_storage(self) -> int:
        if self.vsc["enable_storage"]:
            V_mid_prot_uV = 1 if (self.vsc["V_mid_uV"] < 1) else self.vsc["V_mid_uV"]
            P_sum_fW = self.vsc["P_inp_fW"] - self.vsc["P_out_fW"]
            I_mid_nA = P_sum_fW / V_mid_prot_uV
            dV_mid_uV = I_mid_nA * self.vsc["Constant_us_per_nF"]
            self.vsc["V_mid_uV"] += dV_mid_uV

        if self.vsc["V_mid_uV"] > self.vsc["V_intermediate_max_uV"]:
            self.vsc["V_mid_uV"] = self.vsc["V_intermediate_max_uV"]
        if (not self.vsc["enable_boost"]) and (self.vsc["P_inp_fW"] > 0) and (self.vsc["V_mid_uV"] > self.vsc["V_input_uV"]):
            self.vsc["V_mid_uV"] = self.vsc["V_input_uV"]
        elif self.vsc["V_mid_uV"] < 1:
            self.vsc["V_mid_uV"] = 1
        return round(self.vsc["V_mid_uV"])  # return NOT original, added for easier testing

    def update_states_and_output(self) -> int:

        self.vsc["sample_count"] += 1
        check_thresholds = self.vsc["sample_count"] >= self.vsc["interval_check_thresholds_n"]

        if check_thresholds:
            self.vsc["sample_count"] = 0
            if self.vsc["is_outputting"]:
                if self.vsc["V_mid_uV"] < self.vsc["V_disable_output_threshold_uV"]:
                    self.vsc["is_outputting"] = False
            else:
                if self.vsc["V_mid_uV"] >= self.vsc["V_enable_output_threshold_uV"]:
                    self.vsc["is_outputting"] = True
                    self.vsc["V_mid_uV"] -= self.vsc["dV_enable_output_uV"]

        if check_thresholds or self.vsc["immediate_pwr_good_signal"]:
            # emulate power-good-signal
            if self.vsc["power_good"]:
                if self.vsc["V_mid_uV"] <= self.vsc["V_pwr_good_disable_threshold_uV"]:
                    self.vsc["power_good"] = False
            else:
                if self.vsc["V_mid_uV"] >= self.vsc["V_pwr_good_enable_threshold_uV"]:
                    self.vsc["power_good"] = self.vsc["is_outputting"]

        if self.vsc["is_outputting"] or (self.vsc["interval_startup_disabled_drain_n"]):
            if (not self.vsc["enable_buck"]) or (self.vsc["V_mid_uV"] <= self.vsc["V_output_uV"] + self.vsc["V_buck_drop_uV"]):
                if self.vsc["V_mid_uV"] > self.vsc["V_buck_drop_uV"]:
                    self.vsc["V_out_dac_uV"] = self.vsc["V_mid_uV"] - self.vsc["V_buck_drop_uV"]
                else:
                    self.vsc["V_out_dac_uV"] = 0
            else:
                self.vsc["V_out_dac_uV"] = self.vsc["V_output_uV"]
            self.vsc["V_out_dac_raw"] = self.conv_uV_to_dac_raw(self.vsc["V_out_dac_uV"])
        else:
            self.vsc["V_out_dac_uV"] = 0
            self.vsc["V_out_dac_raw"] = 0

        self.vsc["vsource_skip_gpio_logging"] = (self.vsc["V_out_dac_uV"] < self.vsc["V_output_log_gpio_threshold_uV"])
        return self.vsc["V_out_dac_raw"]

    def conv_adc_raw_to_nA(self, current_raw: int) -> float:
        return self.cal.convert_raw_to_value("emulation", "adc_current", current_raw) * (10 ** 9)

    def conv_uV_to_dac_raw(self, voltage_uV: int) -> int:
        dac_raw = self.cal.convert_value_to_raw("emulation", "dac_voltage_b", float(voltage_uV) / (10 ** 6))
        if dac_raw > (2 ** 16) - 1:
            dac_raw = (2 ** 16) - 1
        return dac_raw

    def get_input_efficiency(self, voltage_uV: int, current_nA: int) -> float:
        voltage_n = int(voltage_uV / (2 ** self.vsc["LUT_input_V_min_log2_uV"]))
        current_n = int(current_nA / (2 ** self.vsc["LUT_input_I_min_log2_nA"]))
        pos_v = int(voltage_n) if (voltage_n > 0) else 0  # V-Scale is Linear!
        pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
        if pos_v >= self.vsc["LUT_size"]:
            pos_v = self.vsc["LUT_size"] - 1
        if pos_c >= self.vsc["LUT_size"]:
            pos_c = self.vsc["LUT_size"] - 1
        return self.vsc["LUT_inp_efficiency_n8"][pos_v * self.vsc["LUT_size"] + pos_c] / (2 ** 8)

    def get_output_inv_efficiency(self, current_nA) -> float:
        current_n = int(current_nA / (2 ** self.vsc["LUT_output_I_min_log2_nA"]))
        pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
        if pos_c >= self.vsc["LUT_size"]:
            pos_c = self.vsc["LUT_size"] - 1
        return self.vsc["LUT_out_inv_efficiency_n4"][pos_c] / (2 ** 4)

    def set_P_input_fW(self, value: int) -> NoReturn:
        self.vsc["P_inp_fW"] = value

    def set_P_output_fW(self, value: int) -> NoReturn:
        self.vsc["P_out_fW"] = value

    def set_V_intermediate_uV(self, value: int) -> NoReturn:
        self.vsc["V_mid_uV"] = value

    def get_P_input_fW(self) -> int:
        return round(self.vsc["P_inp_fW"])

    def get_P_output_fW(self) -> int:
        return round(self.vsc["P_out_fW"])

    def get_V_intermediate_uV(self) -> int:
        return round(self.vsc["V_mid_uV"])

    def get_V_intermediate_raw(self):
        return round(self.conv_uV_to_dac_raw(self.vsc["V_mid_uV"]))

    def get_power_good(self):
        return self.vsc["power_good"]

    def get_I_mod_out_nA(self) -> int:
        return self.vsc["P_out_fW"] / self.vsc["V_mid_uV"]

    def get_state_log_intermediate(self) -> bool:
        return self.vsc["enable_log_mid"]

    def get_state_log_gpio(self) -> bool:
        return self.vsc["vsource_skip_gpio_logging"]

    # TEST-SIMPLIFICATION - code below is not part of pru-code
    def iterate(self, V_in_uV: int = 0, A_in_nA: int = 0, A_out_nA: int = 0):
        self.calc_inp_power(V_in_uV, A_in_nA)
        A_out_raw = self.cal.convert_value_to_raw("emulation", "adc_current", A_out_nA * 10**-9)
        self.calc_out_power(A_out_raw)
        self.update_cap_storage()
        V_out_raw = self.update_states_and_output()
        V_out_uV = int(self.cal.convert_raw_to_value("emulation", "dac_voltage_b", V_out_raw) * 10**6)
        self.P_in_fW += V_in_uV * A_in_nA
        self.P_out_fW += V_out_uV * A_out_nA
        return V_out_uV
