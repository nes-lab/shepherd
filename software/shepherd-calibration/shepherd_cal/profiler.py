"""

This program verifies a proper function of the shepherd frontends for emulator and harvester.
- a SMU is used to step through various voltage and current combinations
- runs from 0 to 5 V and 0 to 50 mA with about 600 combinations
- pru also samples 1 s of data (100k datapoints) from ADCs
- this tracking allows to show influence of design-changes
- "profile_frontend_plot.py" can be used to analyze the data

"""
import itertools
import time
from typing import List
from typing import Tuple

import msgpack
import msgpack_numpy
import numpy as np
import shepherd_core.calibration_hw_def as cal_def
from keithley2600.keithley_driver import KeithleyClass
from shepherd_core.data_models.testbed.cape import TargetPort

from .calibrator import Calibrator
from .logger import logger

INSTR_PROFILE_SHP = """
---------------------- Characterize Shepherd-Frontend -----------------------
- remove targets from target-ports
- remove harvesting source from harvester-input (P6)
- Connect SMU channel A Lo to P10-1 (Target-A GND)
- Connect SMU channel A Hi to P10-2 (Target-A Voltage)
- Resistor (~200 Ohm) and Cap (1-10 uF) between
    - P11-1 (Target-B GND)
    - P11-2 (Target-B Voltage)
- Connect SMU channel B Lo to P6-1 (HRV-Input GND)
- Connect SMU channel B Hi to P6-2/4 (VSense, VHarv -> connected together)
"""


class Profiler:
    def __init__(self, calibrator: Calibrator, short: bool = False):
        self._cal: Calibrator = calibrator

        if short:
            self.voltages_V: np.ndarray = np.append(
                [5.0, 0.05],
                np.arange(0.0, 5.1, 0.4),
            )
            self.currents_A: List[float] = [
                0e-6,
                1e-6,
                2e-6,
                5e-6,
                10e-6,
                50e-6,
                100e-6,
                500e-6,
                1e-3,
                5e-3,
                10e-3,
                15e-3,
                20e-3,
                25e-3,
                30e-3,
                35e-3,
                40e-3,
                45e-3,
                50e-3,
            ]
        else:
            self.voltages_V: np.ndarray = np.append([0.05], np.arange(0.0, 5.1, 0.2))
            self.currents_A: List[float] = [
                0e-6,
                1e-6,
                2e-6,
                5e-6,
                10e-6,
                20e-6,
                50e-6,
                100e-6,
                200e-6,
                500e-6,
                1e-3,
                2e-3,
                5e-3,
                10e-3,
                15e-3,
                20e-3,
                25e-3,
                30e-3,
                35e-3,
                40e-3,
                45e-3,
                50e-3,
            ]

    def measure_emulator_setpoint(
        self,
        smu: KeithleyClass,
        voltage_V: float,
        current_A: float = 0,
    ) -> Tuple[np.ndarray, float, float]:
        voltage_V = min(max(voltage_V, 0.0), 5.0)

        # negative current, because smu acts as a drain
        if smu is not None:
            self._cal.set_smu_to_isource(smu, -current_A, limit_v=5.0)

        # write both dac-channels of emulator
        dac_voltage_raw = self._cal.sheep.convert_value_to_raw(
            "emulator",
            "dac_V_A",
            voltage_V,
        )
        self._cal.sheep.set_aux_target_voltage_raw(
            (2**20) + dac_voltage_raw,
            also_main=True,
        )
        adc_data = self._cal.sheep.sample_from_pru(10)
        adc_currents_raw = msgpack.unpackb(adc_data, object_hook=msgpack_numpy.decode)[
            0
        ]
        adc_current_raw = float(np.mean(adc_currents_raw))

        # voltage measurement only for reference
        if smu is not None:
            smu_voltage = smu.measure.v()
            smu.source.output = smu.OUTPUT_OFF
        else:
            smu_voltage = voltage_V
            current_A = self._cal.sheep.convert_raw_to_value(
                "emulator",
                "adc_C_A",
                adc_current_raw,
            )

        logger.info(
            "  DAC @ %.3f V;"
            " \tSMU: %.3f mA @ %.4f V; "
            " \tI_raw: mean=%.2f, stddev=%.2f",
            voltage_V,
            1000 * current_A,
            smu_voltage,
            adc_current_raw,
            np.std(adc_currents_raw),
        )

        return adc_currents_raw, smu_voltage, current_A

    # TODO: the two meas-FNs could be the same if pru would fill
    def measure_harvester_setpoint(
        self,
        smu: KeithleyClass,
        voltage_V: float,
        current_A: float = 0,
    ) -> Tuple[np.ndarray, np.ndarray, float, float]:
        voltage_V = min(max(voltage_V, 0.0), 5.0)

        # SMU as current-source
        current_A = self._cal.set_smu_to_isource(smu, current_A, limit_v=5.0)

        # write both dac-channels of emulator
        dac_voltage_raw = self._cal.sheep.convert_value_to_raw(
            "harvester",
            "dac_V_Hrv",
            voltage_V,
        )
        self._cal.sheep.set_aux_target_voltage_raw(
            (2**20) + dac_voltage_raw,
            also_main=True,
        )
        adc_data = self._cal.sheep.sample_from_pru(10)
        adc_currents_raw = msgpack.unpackb(adc_data, object_hook=msgpack_numpy.decode)[
            0
        ]
        adc_current_raw = float(np.mean(adc_currents_raw))
        adc_voltages_raw = msgpack.unpackb(adc_data, object_hook=msgpack_numpy.decode)[
            1
        ]
        adc_voltage_raw = float(np.mean(adc_voltages_raw))
        voltage_adc_V = self._cal.sheep.convert_raw_to_value(
            "harvester",
            "adc_V_Sense",
            adc_voltage_raw,
        )

        smu_voltage = smu.measure.v()
        smu.source.output = smu.OUTPUT_OFF

        logger.info(
            "  DAC @ %.3f V;"
            " \tSMU: %.3f mA @ %.4f V;"
            " \tI_raw: mean=%.2f, stddev=%.2f;"
            " \tV_raw: mean=%.2f, stddev=%.2f -> %.4f V",
            voltage_V,
            1000 * current_A,
            smu_voltage,
            adc_current_raw,
            np.std(adc_currents_raw),
            adc_voltage_raw,
            np.std(adc_voltages_raw),
            voltage_adc_V,
        )

        return adc_currents_raw, adc_voltages_raw, smu_voltage, current_A

    def measure_harvester(self) -> np.ndarray:
        logger.info("Measurement - Harvester - Voltage & Current")
        if True:  # TODO: test if leakage is fixed
            self._cal.sheep.switch_shepherd_mode("hrv_adc_read")
            self._cal.sheep.set_aux_target_voltage_raw((2**20) + 0, also_main=True)
            self._cal.sheep.set_shepherd_pcb_power(False)
            time.sleep(2)
            self._cal.sheep.set_shepherd_pcb_power(True)
        self._cal.sheep.switch_shepherd_mode("hrv_adc_read")
        results = np.zeros(
            [6, len(self.voltages_V) * len(self.currents_A)],
            dtype=object,
        )
        for index, (voltage, current) in enumerate(
            itertools.product(self.voltages_V, self.currents_A),
        ):
            (
                c_adc_raw,
                v_dac_raw,
                v_smu_meas,
                c_smu_set,
            ) = self.measure_harvester_setpoint(self._cal.kth.smub, voltage, current)
            # order from Profiler.elem_dict
            results[0][index] = voltage
            results[1][index] = v_dac_raw
            results[2][index] = v_smu_meas
            results[3][index] = current
            results[4][index] = c_adc_raw
            results[5][index] = c_smu_set
        # return to neutral mode
        self._cal.sheep.set_aux_target_voltage_raw(
            (2**20) + cal_def.dac_voltage_to_raw(5.0),
            also_main=True,
        )
        return results

    def measure_emulator_a(self) -> np.ndarray:
        logger.info("Measurement - Emulator - Current - ADC Channel A - Target A")
        self._cal.sheep.switch_shepherd_mode("emu_adc_read")
        results = np.zeros(
            [6, len(self.voltages_V) * len(self.currents_A)],
            dtype=object,
        )
        self._cal.sheep.select_port_for_power_tracking(TargetPort.A)
        # targetA-Port will get the monitored dac-channel-b
        for index, (voltage, current) in enumerate(
            itertools.product(self.voltages_V, self.currents_A),
        ):
            cdata, v_meas, c_set = self.measure_emulator_setpoint(
                self._cal.kth.smua,
                voltage,
                current,
            )
            # order from Profiler.elem_dict
            results[0][index] = voltage
            results[1][index] = self._cal.sheep.convert_value_to_raw(
                "emulator",
                "dac_V_B",
                voltage,
            )
            results[2][index] = v_meas
            results[3][index] = current
            results[4][index] = cdata
            results[5][index] = c_set
        return results

    def measure_emulator_b(self) -> np.ndarray:
        logger.info("Measurement - Emulator - Current - ADC Channel A - Target B")
        self._cal.sheep.switch_shepherd_mode("emu_adc_read")
        results = np.zeros([6, len(self.voltages_V)], dtype=object)
        self._cal.sheep.select_port_for_power_tracking(TargetPort.B)
        # targetB-Port will get the monitored dac-channel-b
        for index, voltage in enumerate(self.voltages_V):
            cdata, v_meas, c_shp = self.measure_emulator_setpoint(None, voltage)
            # order from Profiler.elem_dict
            results[0][index] = voltage
            results[1][index] = self._cal.sheep.convert_value_to_raw(
                "emulator",
                "dac_V_B",
                voltage,
            )
            results[2][index] = v_meas  # is equal to "voltage"-var
            results[3][index] = c_shp
            results[4][index] = cdata
            results[5][index] = c_shp
        return results
