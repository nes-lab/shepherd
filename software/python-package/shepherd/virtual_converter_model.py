"""

this is ported py-version of the pru-code, goals:
- stay close to original code-base
- offer a comparison for the tests
- step 1 to a virtualization of emulation

NOTE: DO NOT OPTIMIZE -> stay close to original code-base

Compromises:
- bitshifted values (ie. _n28) are converted to float without shift

"""

import math
from typing import Optional

from shepherd_core import CalibrationEmulator

from .virtual_source_config import VirtualSourceConfig


class PruCalibration:
    """part of calibration.h"""

    def __init__(self, cal_emu: Optional[CalibrationEmulator] = None):
        self.cal = cal_emu if cal_emu else CalibrationEmulator()

    def conv_adc_raw_to_nA(self, current_raw: int) -> float:
        return self.cal.adc_C_A.raw_to_si(current_raw) * (10**9)
        # TODO: add feature "negative residue compensation" to here

    def conv_adc_raw_to_uV(self, voltage_raw: int) -> float:
        raise RuntimeError("This Fn should not been used")

    def conv_uV_to_dac_raw(self, voltage_uV: float) -> int:
        dac_raw = self.cal.dac_V_A.si_to_raw(float(voltage_uV) / (10**6))
        if dac_raw > (2**16) - 1:
            dac_raw = (2**16) - 1
        return dac_raw


class KernelConverterStruct:
    """part of commons.h"""

    def __init__(self, vs_data: VirtualSourceConfig):
        # NOTE:
        #  - yaml is based on si-units like nA, mV, ms, uF
        #  - c-code and py-copy is using nA, uV, ns, nF, fW, raw
        values = vs_data.export_for_sysfs()

        # generate a new dict from raw_list (that is intended for PRU / sys_fs, see commons.h)
        self.LUT_size: int = 12

        # General Reg Config
        self.converter_mode: int = values[0]
        self.interval_startup_delay_drain_n: int = values[1]

        self.V_input_max_uV: int = values[2]
        self.I_input_max_nA: int = values[3]
        self.V_input_drop_uV: int = values[4]
        self.R_input_kOhm: int = values[5] / (2**22)

        self.Constant_us_per_nF: float = values[6] / (2**28)
        self.V_intermediate_init_uV: int = values[7]  # allow a proper / fast startup
        self.I_intermediate_leak_nA: int = values[8]

        self.V_enable_output_threshold_uV: int = values[
            9
        ]  # -> target gets connected (hysteresis-combo with next value)
        self.V_disable_output_threshold_uV: int = values[
            10
        ]  # -> target gets disconnected
        self.dV_enable_output_uV: int = values[11]
        self.interval_check_thresholds_n: int = values[
            12
        ]  # some BQs check every 65 ms if output should be disconnected

        self.V_pwr_good_enable_threshold_uV: int = values[
            13
        ]  # range where target is informed by output-pin
        self.V_pwr_good_disable_threshold_uV: int = values[14]
        self.immediate_pwr_good_signal: int = values[15]

        self.V_output_log_gpio_threshold_uV: int = values[16]

        # boost converter
        self.V_input_boost_threshold_uV: int = values[
            17
        ]  # min input-voltage for the boost converter to work
        self.V_intermediate_max_uV: int = values[18]  # -> boost shuts off

        # Buck Boost, ie. BQ25570)
        self.V_output_uV: int = values[19]
        self.V_buck_drop_uV: int = values[20]

        # LUTs
        self.LUT_input_V_min_log2_uV: int = values[21]
        self.LUT_input_I_min_log2_nA: int = values[22]
        self.LUT_output_I_min_log2_nA: int = values[23]
        self.LUT_inp_efficiency_n8: list[int] = values[
            24
        ]  # depending on inp_voltage, inp_current, (cap voltage),
        self.LUT_out_inv_efficiency_n4: list[int] = values[
            25
        ]  # depending on output_current


class VirtualConverterModel:
    def __init__(self, config: KernelConverterStruct, calibration: PruCalibration):
        self._cal: PruCalibration = calibration
        self._cfg: KernelConverterStruct = config

        # boost internal state
        self.V_input_uV: float = 0.0
        self.P_inp_fW: float = 0.0
        self.P_out_fW: float = 0.0
        self.interval_startup_disabled_drain_n: int = (
            self._cfg.interval_startup_delay_drain_n
        )

        # container for the stored energy
        self.V_mid_uV: float = self._cfg.V_intermediate_init_uV

        # buck internal state
        self.enable_storage: bool = (int(self._cfg.converter_mode) & 0b0001) > 0
        self.enable_boost: bool = (int(self._cfg.converter_mode) & 0b0010) > 0
        self.enable_buck: bool = (int(self._cfg.converter_mode) & 0b0100) > 0
        self.enable_log_mid: bool = (int(self._cfg.converter_mode) & 0b1000) > 0

        self.V_out_dac_uV: float = self._cfg.V_output_uV
        self.V_out_dac_raw: int = self._cal.conv_uV_to_dac_raw(self._cfg.V_output_uV)
        self.power_good: bool = True

        # prepare hysteresis-thresholds
        self.dV_enable_output_uV: float = self._cfg.dV_enable_output_uV
        self.V_enable_output_threshold_uV: float = (
            self._cfg.V_enable_output_threshold_uV
        )
        self.V_disable_output_threshold_uV: float = (
            self._cfg.V_disable_output_threshold_uV
        )

        if self.dV_enable_output_uV > self.V_enable_output_threshold_uV:
            self.V_enable_output_threshold_uV = self.dV_enable_output_uV

        # pulled from update_states_and_output() due to easier static init
        self.sample_count: int = 0xFFFFFFF0
        self.is_outputting: bool = True
        self.vsource_skip_gpio_logging: bool = False

    def calc_inp_power(self, input_voltage_uV: float, input_current_nA: float) -> int:
        # Next 2 lines are Python-specific
        input_voltage_uV = max(0.0, input_voltage_uV)
        input_current_nA = max(0.0, input_current_nA)

        if input_voltage_uV > self._cfg.V_input_drop_uV:
            input_voltage_uV -= self._cfg.V_input_drop_uV
        else:
            input_voltage_uV = 0.0

        if input_voltage_uV > self._cfg.V_input_max_uV:
            input_voltage_uV = self._cfg.V_input_max_uV

        if input_current_nA > self._cfg.I_input_max_nA:
            input_current_nA = self._cfg.I_input_max_nA

        self.V_input_uV = input_voltage_uV

        if self.enable_boost:
            if input_voltage_uV < self._cfg.V_input_boost_threshold_uV:
                input_voltage_uV = 0.0
            if input_voltage_uV > self.V_mid_uV:
                input_voltage_uV = self.V_mid_uV
        elif not self.enable_storage:
            # direct connection
            self.V_mid_uV = input_voltage_uV
            input_voltage_uV = 0.0
        else:
            if input_voltage_uV > self.V_mid_uV:
                V_diff_uV = input_voltage_uV - self.V_mid_uV
                V_drop_uV = input_current_nA * self._cfg.R_input_kOhm
                if V_drop_uV > V_diff_uV:
                    input_voltage_uV = self.V_mid_uV
                else:
                    input_voltage_uV -= V_drop_uV
            else:
                input_voltage_uV = 0.0

        if self.enable_boost:
            eta_inp = self.get_input_efficiency(input_voltage_uV, input_current_nA)
        else:
            eta_inp = 1.0

        self.P_inp_fW = eta_inp * input_voltage_uV * input_current_nA
        return round(self.P_inp_fW)  # Python-specific, added for easier testing

    def calc_out_power(self, current_adc_raw: int) -> int:
        # Next 2 lines are Python-specific
        current_adc_raw = max(0, current_adc_raw)
        current_adc_raw = min((2**18) - 1, current_adc_raw)

        P_leak_fW = self.V_mid_uV * self._cfg.I_intermediate_leak_nA
        I_out_nA = self._cal.conv_adc_raw_to_nA(current_adc_raw)
        if self.enable_buck:
            eta_inv_out = self.get_output_inv_efficiency(I_out_nA)
        else:
            eta_inv_out = 1.0

        self.P_out_fW = eta_inv_out * self.V_out_dac_uV * I_out_nA + P_leak_fW

        if self.interval_startup_disabled_drain_n > 0:
            self.interval_startup_disabled_drain_n -= 1
            self.P_out_fW = 0.0

        return round(self.P_out_fW)  # Python-specific, added for easier testing

    # TODO: add range-checks for add, sub Ops
    def update_cap_storage(self) -> int:
        if self.enable_storage:
            V_mid_prot_uV = max(1.0, self.V_mid_uV)
            P_sum_fW = self.P_inp_fW - self.P_out_fW
            I_mid_nA = P_sum_fW / V_mid_prot_uV
            dV_mid_uV = I_mid_nA * self._cfg.Constant_us_per_nF
            self.V_mid_uV += dV_mid_uV

        if self.V_mid_uV > self._cfg.V_intermediate_max_uV:
            self.V_mid_uV = self._cfg.V_intermediate_max_uV
        if (
            (not self.enable_boost)
            and (self.P_inp_fW > 0.0)
            and (self.V_mid_uV > self.V_input_uV)
        ):
            self.V_mid_uV = self.V_input_uV
        elif self.V_mid_uV < 1:
            self.V_mid_uV = 1
        return round(self.V_mid_uV)  # Python-specific, added for easier testing

    def update_states_and_output(self) -> int:
        self.sample_count += 1
        check_thresholds = self.sample_count >= self._cfg.interval_check_thresholds_n

        if check_thresholds:
            self.sample_count = 0
            if self.is_outputting:
                if self.V_mid_uV < self.V_disable_output_threshold_uV:
                    self.is_outputting = False
            else:
                if self.V_mid_uV >= self.V_enable_output_threshold_uV:
                    self.is_outputting = True
                    self.V_mid_uV -= self.dV_enable_output_uV

        if check_thresholds or self._cfg.immediate_pwr_good_signal:
            # generate power-good-signal
            if self.power_good:
                if self.V_mid_uV <= self._cfg.V_pwr_good_disable_threshold_uV:
                    self.power_good = False
            else:
                if self.V_mid_uV >= self._cfg.V_pwr_good_enable_threshold_uV:
                    self.power_good = self.is_outputting
            # set batok pin to state ... TODO?

        if self.is_outputting or self.interval_startup_disabled_drain_n > 0:
            if (not self.enable_buck) or (
                self.V_mid_uV <= self._cfg.V_output_uV + self._cfg.V_buck_drop_uV
            ):
                if self.V_mid_uV > self._cfg.V_buck_drop_uV:
                    self.V_out_dac_uV = self.V_mid_uV - self._cfg.V_buck_drop_uV
                else:
                    self.V_out_dac_uV = 0.0
            else:
                self.V_out_dac_uV = self._cfg.V_output_uV
            self.V_out_dac_raw = self._cal.conv_uV_to_dac_raw(self.V_out_dac_uV)
        else:
            self.V_out_dac_uV = 0.0
            self.V_out_dac_raw = 0

        self.vsource_skip_gpio_logging = (
            self.V_out_dac_uV < self._cfg.V_output_log_gpio_threshold_uV
        )
        return self.V_out_dac_raw

    def get_input_efficiency(self, voltage_uV: float, current_nA: float) -> float:
        voltage_n = int(voltage_uV / (2**self._cfg.LUT_input_V_min_log2_uV))
        current_n = int(current_nA / (2**self._cfg.LUT_input_I_min_log2_nA))
        pos_v = int(voltage_n) if (voltage_n > 0) else 0  # V-Scale is Linear!
        pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
        if pos_v >= self._cfg.LUT_size:
            pos_v = self._cfg.LUT_size - 1
        if pos_c >= self._cfg.LUT_size:
            pos_c = self._cfg.LUT_size - 1
        return self._cfg.LUT_inp_efficiency_n8[pos_v * self._cfg.LUT_size + pos_c] / (
            2**8
        )

    def get_output_inv_efficiency(self, current_nA: float) -> float:
        current_n = int(current_nA / (2**self._cfg.LUT_output_I_min_log2_nA))
        pos_c = int(math.log2(current_n)) if (current_n > 0) else 0
        if pos_c >= self._cfg.LUT_size:
            pos_c = self._cfg.LUT_size - 1
        return self._cfg.LUT_out_inv_efficiency_n4[pos_c] / (2**4)

    def set_P_input_fW(self, value: float) -> None:
        self.P_inp_fW = value

    def set_P_output_fW(self, value: float) -> None:
        self.P_out_fW = value

    def set_V_intermediate_uV(self, value: float) -> None:
        self.V_mid_uV = value

    def get_P_input_fW(self) -> int:
        return round(self.P_inp_fW)

    def get_P_output_fW(self) -> int:
        return round(self.P_out_fW)

    def get_V_intermediate_uV(self) -> int:
        return round(self.V_mid_uV)

    def get_V_intermediate_raw(self):
        return round(self._cal.conv_uV_to_dac_raw(self.V_mid_uV))

    def get_power_good(self):
        return self.power_good

    def get_I_mod_out_nA(self) -> float:
        return self.P_out_fW / self.V_mid_uV

    def get_state_log_intermediate(self) -> bool:
        return self.enable_log_mid

    def get_state_log_gpio(self) -> bool:
        return self.vsource_skip_gpio_logging
