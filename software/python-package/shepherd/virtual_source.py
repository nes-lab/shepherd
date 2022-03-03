from typing import NoReturn
from shepherd import VirtualSourceData, CalibrationData
import math
# TODO: rename VirtualSourceModel

class VirtualSource(object):
    """
    this is ported py-version of the pru-code, goals:
    - stay close to original code-base
    - offer a comparison for the tests
    - step 1 to a virtualization of emulation
    NOTE: DO NOT OPTIMIZE -> stay close to original code-base
    """

    _cal = CalibrationData.from_default()

    def __init__(self, setting, calibration: CalibrationData):
        """

        :param setting: YAML-Path, dict, or converter-name
        """
        if calibration is not None:
            self._cal = calibration

        # NOTE:
        #  - yaml is based on si-units like nA, mV, ms, uF
        #  - c-code and py-copy is using nA, uV, ns, nF, fW, raw
        setting = VirtualSourceData(setting)
        values = setting.export_for_sysfs()

        # generate a new dict from raw_list (that is intended for PRU / sys_fs, see commons.h)
        self.LUT_size = 12

        # General Reg Config
        self.converter_mode = values[0]
        self.interval_startup_disabled_drain_n = values[1]

        self.V_input_max_uV = values[2]
        self.I_input_max_nA = values[3]
        self.V_input_drop_uV = values[4]
        self.Constant_1k_per_Ohm = values[5]

        self.Constant_us_per_nF = values[6] / (2 ** 28)
        self.V_intermediate_init_uV = values[7]  # allow a proper / fast startup
        self.I_intermediate_leak_nA = values[8]

        self.V_enable_output_threshold_uV = values[9]  # -> target gets connected (hysteresis-combo with next value)
        self.V_disable_output_threshold_uV = values[10]  # -> target gets disconnected
        self.dV_enable_output_uV = values[11]
        self.interval_check_thresholds_n = values[12]  # some BQs check every 65 ms if output should be disconnected

        self.V_pwr_good_enable_threshold_uV = values[13]  # range where target is informed by output-pin
        self.V_pwr_good_disable_threshold_uV = values[14]
        self.immediate_pwr_good_signal = values[15]

        self.V_output_log_gpio_threshold_uV = values[16]

        # boost converter
        self.V_input_boost_threshold_uV = values[17]  # min input-voltage for the boost converter to work
        self.V_intermediate_max_uV = values[18]  # -> boost shuts off

        # Buck Boost, ie. BQ25570)
        self.V_output_uV = values[19]
        self.V_buck_drop_uV = values[20]

        # LUTs
        self.LUT_input_V_min_log2_uV = values[21]
        self.LUT_input_I_min_log2_nA = values[22]
        self.LUT_output_I_min_log2_nA = values[23]
        self.LUT_inp_efficiency_n8 = values[24]  # depending on inp_voltage, inp_current, (cap voltage),
        self.LUT_out_inv_efficiency_n4 = values[25]  # depending on output_current

        # boost internal state
        self.V_input_uV = 0.0
        self.P_inp_fW = 0.0
        self.P_out_fW = 0.0

        # container for the stored energy
        self.V_mid_uV = self.V_intermediate_init_uV

        # buck internal state
        self.enable_storage = (int(self.converter_mode) & 0b0001) > 0
        self.enable_boost = (int(self.converter_mode) & 0b0010) > 0
        self.enable_buck = (int(self.converter_mode) & 0b0100) > 0
        self.enable_log_mid = (int(self.converter_mode) & 0b1000) > 0

        self.V_out_dac_uV = self.V_output_uV
        self.V_out_dac_raw = self.conv_uV_to_dac_raw(self.V_out_dac_uV)
        self.power_good = True

        # prepare hysteresis-thresholds
        if self.dV_enable_output_uV > self.V_enable_output_threshold_uV:
            self.V_enable_output_threshold_uV = self.dV_enable_output_uV

        # pulled from update_states_and_output() due to easier static init
        self.sample_count = 0xFFFFFFF0
        self.is_outputting = True

        self.vsource_skip_gpio_logging = False

        # TEST-SIMPLIFICATION - code below is not part of pru-code
        self.P_in_fW: float = 0
        self.P_out_fW: float = 0

    def calc_inp_power(self, input_voltage_uV: int, input_current_nA: int) -> int:
        if input_voltage_uV < 0:
            input_voltage_uV = 0
        if input_current_nA < 0:
            input_current_nA = 0

        if input_voltage_uV > self.V_input_drop_uV:
            input_voltage_uV -= self.V_input_drop_uV
        else:
            input_voltage_uV = 0

        if input_voltage_uV > self.V_input_max_uV:
            input_voltage_uV = self.V_input_max_uV

        if input_current_nA > self.I_input_max_nA:
            input_current_nA = self.I_input_max_nA

        self.V_input_uV = input_voltage_uV

        if self.enable_boost:
            if input_voltage_uV < self.V_input_boost_threshold_uV:
                input_voltage_uV = 0
            if input_voltage_uV > self.V_mid_uV:
                input_voltage_uV = self.V_mid_uV
        elif not self.enable_storage:
            # direct connection
            self.V_mid_uV = input_voltage_uV
            input_voltage_uV = 0
        else:
            if input_voltage_uV > self.V_mid_uV:
                I_max_nA = (input_voltage_uV - self.V_mid_uV) * self.Constant_1k_per_Ohm
                if input_current_nA > I_max_nA:
                    input_current_nA = I_max_nA
                input_voltage_uV = self.V_mid_uV
            else:
                input_voltage_uV = 0

        if self.enable_boost:
            eta_inp = self.get_input_efficiency(input_voltage_uV, input_current_nA)
        else:
            eta_inp = 1.0

        self.P_inp_fW = input_voltage_uV * input_current_nA * eta_inp
        return round(self.P_inp_fW)  # return NOT original, added for easier testing

    def calc_out_power(self, current_adc_raw: int) -> int:
        if current_adc_raw < 0:
            current_adc_raw = 0
        elif current_adc_raw >= (2 ** 18):
            current_adc_raw = (2 ** 18) - 1

        P_leak_fW = self.V_mid_uV * self.I_intermediate_leak_nA
        I_out_nA = self.conv_adc_raw_to_nA(current_adc_raw)
        if self.enable_buck:
            eta_inv_out = self.get_output_inv_efficiency(I_out_nA)
        else:
            eta_inv_out = 1.0

        self.P_out_fW = I_out_nA * self.V_out_dac_uV * eta_inv_out + P_leak_fW

        if self.interval_startup_disabled_drain_n > 0:
            self.interval_startup_disabled_drain_n -= 1
            self.P_out_fW = 0

        return round(self.P_out_fW)  # return NOT original, added for easier testing

    def update_cap_storage(self) -> int:
        if self.enable_storage:
            V_mid_prot_uV = 1 if (self.V_mid_uV < 1) else self.V_mid_uV
            P_sum_fW = self.P_inp_fW - self.P_out_fW
            I_mid_nA = P_sum_fW / V_mid_prot_uV
            dV_mid_uV = I_mid_nA * self.Constant_us_per_nF
            self.V_mid_uV += dV_mid_uV

        if self.V_mid_uV > self.V_intermediate_max_uV:
            self.V_mid_uV = self.V_intermediate_max_uV
        if (not self.enable_boost) and (self.P_inp_fW > 0) and (self.V_mid_uV > self.V_input_uV):
            self.V_mid_uV = self.V_input_uV
        elif self.V_mid_uV < 1:
            self.V_mid_uV = 1
        return round(self.V_mid_uV)  # return NOT original, added for easier testing

    def update_states_and_output(self) -> int:

        self.sample_count += 1
        check_thresholds = self.sample_count >= self.interval_check_thresholds_n

        if check_thresholds:
            self.sample_count = 0
            if self.is_outputting:
                if self.V_mid_uV < self.V_disable_output_threshold_uV:
                    self.is_outputting = False
            else:
                if self.V_mid_uV >= self.V_enable_output_threshold_uV:
                    self.is_outputting = True
                    self.V_mid_uV -= self.dV_enable_output_uV

        if check_thresholds or self.immediate_pwr_good_signal:
            # generate power-good-signal
            if self.power_good:
                if self.V_mid_uV <= self.V_pwr_good_disable_threshold_uV:
                    self.power_good = False
            else:
                if self.V_mid_uV >= self.V_pwr_good_enable_threshold_uV:
                    self.power_good = self.is_outputting

        if self.is_outputting or self.interval_startup_disabled_drain_n:
            if (not self.enable_buck) or (self.V_mid_uV <= self.V_output_uV + self.V_buck_drop_uV):
                if self.V_mid_uV > self.V_buck_drop_uV:
                    self.V_out_dac_uV = self.V_mid_uV - self.V_buck_drop_uV
                else:
                    self.V_out_dac_uV = 0
            else:
                self.V_out_dac_uV = self.V_output_uV
            self.V_out_dac_raw = self.conv_uV_to_dac_raw(self.V_out_dac_uV)
        else:
            self.V_out_dac_uV = 0
            self.V_out_dac_raw = 0

        self.vsource_skip_gpio_logging = (self.V_out_dac_uV < self.V_output_log_gpio_threshold_uV)
        return self.V_out_dac_raw

    def conv_adc_raw_to_nA(self, current_raw: int) -> float:
        return self._cal.convert_raw_to_value("emulator", "adc_current", current_raw) * (10 ** 9)

    def conv_uV_to_dac_raw(self, voltage_uV: int) -> int:
        dac_raw = self._cal.convert_value_to_raw("emulator", "dac_voltage_b", float(voltage_uV) / (10 ** 6))
        if dac_raw > (2 ** 16) - 1:
            dac_raw = (2 ** 16) - 1
        return dac_raw

    def get_input_efficiency(self, voltage_uV: int, current_nA: int) -> float:
        voltage_n = int(voltage_uV / (2 ** self.LUT_input_V_min_log2_uV))
        current_n = int(current_nA / (2 ** self.LUT_input_I_min_log2_nA))
        pos_v = int(voltage_n) if (voltage_n > 0) else 0  # V-Scale is Linear!
        pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
        if pos_v >= self.LUT_size:
            pos_v = self.LUT_size - 1
        if pos_c >= self.LUT_size:
            pos_c = self.LUT_size - 1
        return self.LUT_inp_efficiency_n8[pos_v * self.LUT_size + pos_c] / (2 ** 8)

    def get_output_inv_efficiency(self, current_nA) -> float:
        current_n = int(current_nA / (2 ** self.LUT_output_I_min_log2_nA))
        pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
        if pos_c >= self.LUT_size:
            pos_c = self.LUT_size - 1
        return self.LUT_out_inv_efficiency_n4[pos_c] / (2 ** 4)

    def set_P_input_fW(self, value: int) -> NoReturn:
        self.P_inp_fW = value

    def set_P_output_fW(self, value: int) -> NoReturn:
        self.P_out_fW = value

    def set_V_intermediate_uV(self, value: int) -> NoReturn:
        self.V_mid_uV = value

    def get_P_input_fW(self) -> int:
        return round(self.P_inp_fW)

    def get_P_output_fW(self) -> int:
        return round(self.P_out_fW)

    def get_V_intermediate_uV(self) -> int:
        return round(self.V_mid_uV)

    def get_V_intermediate_raw(self):
        return round(self.conv_uV_to_dac_raw(self.V_mid_uV))

    def get_power_good(self):
        return self.power_good

    def get_I_mod_out_nA(self) -> int:
        return self.P_out_fW / self.V_mid_uV

    def get_state_log_intermediate(self) -> bool:
        return self.enable_log_mid

    def get_state_log_gpio(self) -> bool:
        return self.vsource_skip_gpio_logging

    # TEST-SIMPLIFICATION - code below is not part of pru-code
    def iterate(self, V_in_uV: int = 0, A_in_nA: int = 0, A_out_nA: int = 0):
        self.calc_inp_power(V_in_uV, A_in_nA)
        A_out_raw = self._cal.convert_value_to_raw("emulator", "adc_current", A_out_nA * 10 ** -9)
        self.calc_out_power(A_out_raw)
        self.update_cap_storage()
        V_out_raw = self.update_states_and_output()
        V_out_uV = int(self._cal.convert_raw_to_value("emulator", "dac_voltage_b", V_out_raw) * 10 ** 6)
        self.P_in_fW += V_in_uV * A_in_nA
        self.P_out_fW += V_out_uV * A_out_nA
        return V_out_uV
