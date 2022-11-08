#!/usr/bin/env python3
import logging
import time
from pathlib import Path
from typing import Union

import msgpack
import msgpack_numpy
import numpy as np
import yaml
import zerorpc
from fabric import Connection
from keithley2600 import Keithley2600
from shepherd.calibration_default import dac_voltage_to_raw
from shepherd.calibration import CalibrationData
from .plot import plot_calibration

INSTR_HRVST = """
---------------------- Harvester calibration -----------------------
- Short P6-2 and P6-4
    - P6-2 -> VSense / Voltage-Measurement of Harvest-Port
    - P6-4 -> VHarv / Current Sink of Harvest-Port
- Connect SMU Channel A & B Lo to GND (P6-1, alternatively P8-1/2)
- Connect SMU Channel A Hi to P6-3 (VSim)
- Connect SMU Channel B Hi to P6-2/4 (VSense, VHarv)
"""

INSTR_EMU = """
---------------------- Emulator calibration -----------------------
- remove targets from target-ports
- Connect SMU channel A Lo to P10-1 (Target-Port A GND)
- Connect SMU channel A Hi to P10-2 (Target-Port A Voltage)
- Connect SMU channel B Lo to P11-1 (Target-Port B GND)
- Connect SMU channel B Hi to P11-2 (Target-Port B Voltage)
"""

INSTR_4WIRE = "- NOTE: be sure to use 4-Wire-Cabling to SMU for improved results"


consoleHandler = logging.StreamHandler()
logger = logging.getLogger("shp.calTool")
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)
# Note: defined here to avoid circular import


def set_verbose_level(verbose: int = 2) -> None:
    if verbose == 0:
        logger.setLevel(logging.ERROR)
    elif verbose == 1:
        logger.setLevel(logging.WARNING)
    elif verbose == 2:
        logger.setLevel(logging.INFO)
    elif verbose > 2:
        logger.setLevel(logging.DEBUG)


class Cal:

    _cnx: Connection = None
    _host: str = None
    _sheep: zerorpc.Client = None
    _kth: Keithley2600() = None

    _pwrline_cycles: float = None
    _mode_4wire: bool = None

    def __init__(self, host, user, password: str = None, smu_ip: str = None, mode_4wire: bool = True, pwrline_cycles: float = 16):

        if password is not None:
            fabric_args = {"password": password}
        else:
            fabric_args = {}

        self._mode_4wire = mode_4wire
        self._pwrline_cycles = min(max(pwrline_cycles, 0.001), 25)

        self._host = host
        self._sheep = zerorpc.Client(timeout=60, heartbeat=20)
        self._cnx = Connection(host, user=user, connect_kwargs=fabric_args)

        if smu_ip is not None:
            self._kth = Keithley2600(f"TCPIP0::{smu_ip}::INSTR")

        # enter
        self._cnx.sudo("systemctl restart shepherd-rpc", hide=True, warn=True)
        self._sheep.connect(f"tcp://{host}:4242")
        if self._kth is not None:
            self._kth.reset()

    def __del__(self):
        # ... overcautious
        self._cnx.sudo("systemctl stop shepherd-rpc", hide=True, warn=True)
        self._cnx.close()
        del self._cnx

    def set_smu_auto_on(self, smu):
        smu.source.output = smu.OUTPUT_ON
        smu.measure.autozero = smu.AUTOZERO_AUTO
        smu.measure.autorangev = smu.AUTORANGE_ON
        smu.measure.autorangei = smu.AUTORANGE_ON
        smu.measure.nplc = self._pwrline_cycles

    def set_smu_to_vsource(self, smu, value_v: float, limit_i: float):
        smu.sense = smu.SENSE_REMOTE if self._mode_4wire else smu.SENSE_LOCAL
        smu.source.levelv = value_v
        smu.source.limiti = limit_i
        smu.source.func = smu.OUTPUT_DCVOLTS
        smu.source.autorangev = smu.AUTORANGE_ON
        self.set_smu_auto_on(smu)

    def set_smu_as_isource(self, smu, value_i: float, limit_v: float):
        smu.sense = smu.SENSE_REMOTE if self._mode_4wire else smu.SENSE_LOCAL
        smu.source.leveli = value_i
        smu.source.limitv = limit_v
        smu.source.func = smu.OUTPUT_DCAMPS
        smu.source.autorangei = smu.AUTORANGE_ON
        self.set_smu_auto_on(smu)

    @staticmethod
    def reject_outliers(data, m=2.0):
        d = np.abs(data - np.median(data))
        mdev = np.median(d)
        s = d / mdev if mdev else 0.0
        return data[s < m]

    def measure_harvester_adc_voltage(self, smu) -> list:

        smu_current_A = 0.1e-3
        smu_voltages_V = np.linspace(0.3, 2.5, 12)
        dac_voltage_V = 4.5
        dac_voltage_raw = dac_voltage_to_raw(dac_voltage_V)

        mode_old = self._sheep.switch_shepherd_mode("hrv_adc_read")
        logger.debug(
            " -> setting dac-voltage to %s V (raw = %s) -> upper limit now max",
            dac_voltage_V,
            dac_voltage_raw,
        )
        self._sheep.set_aux_target_voltage_raw((2 ** 20) + dac_voltage_raw, also_main=True)

        self.set_smu_to_vsource(smu, 0.0, smu_current_A)

        results = []
        for voltage_V in smu_voltages_V:
            smu.source.levelv = voltage_V
            time.sleep(0.5)
            self._sheep.sample_from_pru(2)  # flush previous buffers (just to be safe)

            meas_enc = self._sheep.sample_from_pru(40)  # captures # buffers
            meas_rec = msgpack.unpackb(meas_enc, object_hook=msgpack_numpy.decode)
            adc_current_raw = float(np.mean(self.reject_outliers(meas_rec[0])))

            adc_filtered = self.reject_outliers(meas_rec[1])
            outlier_rate = 100 * (1 - adc_filtered.size / meas_rec[1].size)
            adc_voltage_raw = float(np.mean(adc_filtered))

            smu_current_mA = 1000 * smu.measure.i()

            results.append(
                {"reference_si": float(voltage_V), "shepherd_raw": adc_voltage_raw}
            )
            logger.debug(
                "  SMU-reference: %.4f V @ %.3f mA;"
                "  adc-v: %.4f raw; adc-c: %.3f raw; filtered %.2f %% of values",
                voltage_V,
                smu_current_mA,
                adc_voltage_raw,
                adc_current_raw,
                outlier_rate,
            )

        smu.source.output = smu.OUTPUT_OFF
        self._sheep.switch_shepherd_mode(mode_old)
        return results

    def measure_harvester_adc_current(self, smu) -> list:  # TODO: combine with previous FN

        sm_currents_A = [10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3]
        dac_voltage_V = 2.5
        dac_voltage_raw = dac_voltage_to_raw(dac_voltage_V)

        mode_old = self._sheep.switch_shepherd_mode("hrv_adc_read")
        logger.debug(
            " -> setting dac-voltage to %s V (raw = %s)",
            dac_voltage_V,
            dac_voltage_raw,
        )
        self._sheep.set_aux_target_voltage_raw((2**20) + dac_voltage_raw, also_main=True)

        self.set_smu_as_isource(smu, 0.0, 3.0)

        results = []
        for current_A in sm_currents_A:
            smu.source.leveli = current_A
            time.sleep(0.5)
            self._sheep.sample_from_pru(2)  # flush previous buffers (just to be safe)

            meas_enc = self._sheep.sample_from_pru(40)  # captures # buffers
            meas_rec = msgpack.unpackb(meas_enc, object_hook=msgpack_numpy.decode)
            adc_filtered = self.reject_outliers(meas_rec[0])
            outlier_rate = 100 * (1 - adc_filtered.size / meas_rec[0].size)
            adc_current_raw = float(np.mean(adc_filtered))

            # voltage measurement only for information, drop might appear severe,
            # because 4port-measurement is not active
            smu_voltage = smu.measure.v()

            results.append({"reference_si": current_A, "shepherd_raw": adc_current_raw})
            logger.debug(
                "  SMU-reference: %.3f mA @ %.4f V;"
                "  adc-c: %.4f raw; filtered %.2f %% of values",
                1000 * current_A,
                smu_voltage,
                adc_current_raw,
                outlier_rate,
            )

        smu.source.output = smu.OUTPUT_OFF
        self._sheep.switch_shepherd_mode(mode_old)
        return results

    def measure_emulator_current(self, smu) -> list:

        sm_currents_A = [10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3]
        dac_voltage_V = 2.5

        mode_old = self._sheep.switch_shepherd_mode("emu_adc_read")
        logger.debug(" -> setting dac-voltage to %s V", dac_voltage_V)
        # write both dac-channels of emulator
        self._sheep.set_aux_target_voltage_raw(
            (2**20) + dac_voltage_to_raw(dac_voltage_V), also_main=True
        )  # TODO: rpc seems to have trouble with named parameters, so 2**20 is a bugfix

        self.set_smu_as_isource(smu, 0.0, 3.0)

        results = []
        for current_A in sm_currents_A:
            smu.source.leveli = -current_A  # negative current, because smu acts as a drain
            time.sleep(0.5)
            self._sheep.sample_from_pru(2)  # flush previous buffers (just to be safe)

            meas_enc = self._sheep.sample_from_pru(40)  # captures # buffers
            meas_rec = msgpack.unpackb(meas_enc, object_hook=msgpack_numpy.decode)
            adc_filtered = self.reject_outliers(meas_rec[0])
            outlier_rate = 100 * (1 - adc_filtered.size / meas_rec[0].size)
            adc_current_raw = float(np.mean(adc_filtered))

            # voltage measurement only for information, drop might appear severe,
            # because 4port-measurement is not active
            smu_voltage = smu.measure.v()

            results.append({"reference_si": current_A, "shepherd_raw": adc_current_raw})
            logger.debug(
                "  SMU-reference: %.3f mA @ %.4f V;"
                "  adc-c: %.4f raw; filtered %.2f %% of values",
                1000 * current_A,
                smu_voltage,
                adc_current_raw,
                outlier_rate,
            )

        smu.source.output = smu.OUTPUT_OFF
        self._sheep.switch_shepherd_mode(mode_old)
        return results

    def measure_dac_voltage(self, smu, dac_bitmask) -> list:

        smu_current_A = 0.1e-3
        voltages_V = np.linspace(0.3, 2.5, 12)

        voltages_raw = [dac_voltage_to_raw(val) for val in voltages_V]

        # write both dac-channels of emulator
        self._sheep.dac_write(dac_bitmask, 0)

        self.set_smu_as_isource(smu, smu_current_A, 5.0)
        # TODO: used for emu & hrv, add parameter for drain and src

        results = []
        for _iter, _val in enumerate(voltages_raw):
            self._sheep.dac_write(dac_bitmask, _val)
            time.sleep(0.5)
            smu.measure.v()
            meas_series = []
            for _ in range(30):
                meas_series.append(smu.measure.v())
                time.sleep(0.01)
            mean = float(np.mean(meas_series))
            medi = float(np.median(meas_series))
            smu_current_mA = 1000 * smu.measure.i()

            results.append({"reference_si": mean, "shepherd_raw": _val})
            logger.debug(
                "  shp-dac: %.3f V (%.0f raw);"
                "  SMU-reference: %.6f V (median = %.6f); current: %.3f mA",
                voltages_V[_iter],
                _val,
                mean,
                medi,
                smu_current_mA,
            )

        smu.source.output = smu.OUTPUT_OFF
        return results

    def measure_harvester(self) -> dict:
        results = {}
        logger.info("Measurement - Harvester - ADC . Voltage")
        results["adc_voltage"] = self.measure_harvester_adc_voltage(self._kth.smub)

        logger.info("Measurement - Harvester - ADC . Current")
        results["adc_current"] = self.measure_harvester_adc_current(self._kth.smub)

        logger.info("Measurement - Harvester - DAC . Voltage - Channel A (VSim)")
        results["dac_voltage_a"] = self.measure_dac_voltage(self._kth.smua, 0b0001)

        logger.info("Measurement - Harvester - DAC . Voltage - Channel B (VHarv)")
        results["dac_voltage_b"] = self.measure_dac_voltage(self._kth.smub, 0b0010)
        return results

    def measure_emulator(self) -> dict:
        results = {}
        logger.info("Measurement - Emulator - ADC . Current - Target A")
        # targetA-Port will get the monitored dac-channel-b
        self._sheep.select_target_for_power_tracking(True)
        results["adc_current"] = self.measure_emulator_current(self._kth.smua)

        logger.info("Measurement - Emulator - ADC . Current - Target B")
        # targetB-Port will get the monitored dac-channel-b
        self._sheep.select_target_for_power_tracking(False)
        # NOTE: adc_voltage does not exist for emulator, but gets used for target port B
        results["adc_voltage"] = self.measure_emulator_current(self._kth.smub)

        self._sheep.select_target_for_power_tracking(False)  # routes DAC.A to TGT.A to SMU-A
        logger.info("Measurement - Emulator - DAC . Voltage - Channel A")
        results["dac_voltage_a"] = self.measure_dac_voltage(self._kth.smua, 0b1100)

        logger.info("Measurement - Emulator - DAC . Voltage - Channel B")
        results["dac_voltage_b"] = self.measure_dac_voltage(self._kth.smub, 0b1100)
        return results

    def write(self, cal_file: str, serial: str, version: str, cal_date: str):
        temp_file = "/tmp/calib.yml"
        with open(cal_file) as stream:
            cal_host = yaml.safe_load(stream)['host']
        if cal_host != self._host:
            logger.warning("Calibration data for '%s' doesn't match host '%s'.", cal_host, self._host)

        self._cnx.put(cal_file, temp_file)  # noqa: S108
        logger.info("----------EEPROM WRITE------------")
        result = self._cnx.sudo(
            f"shepherd-sheep eeprom write -v {version} -s {serial} -d {cal_date}"
            f" -c {temp_file}", warn=True, hide=True,
        )
        logger.info(result.stdout)
        logger.info("---------------------------------")

    def read(self):
        logger.info("----------EEPROM READ------------")
        result = self._cnx.sudo("shepherd-sheep eeprom read", warn=True, hide=True)
        logger.info(result.stdout)
        logger.info("---------------------------------")

    def retrieve(self, cal_file: str):
        temp_file = "/tmp/calib.yml"
        result = self._cnx.sudo(f"shepherd-sheep eeprom read -c {temp_file}", warn=True, hide=True)
        logger.info(result.stdout)
        self._cnx.get(temp_file, local=str(cal_file))

    @staticmethod
    def convert(meas_file: Path, cal_file: Union[None, Path] = None, do_plot: bool = False) -> Path:
        with open(meas_file) as stream:
            meas_data = yaml.safe_load(stream)
            meas_dict = meas_data["measurements"]

        calib_dict = CalibrationData.from_measurements(meas_file).data

        if do_plot:
            plot_calibration(meas_dict, calib_dict, meas_file)

        out_dict = {"node": meas_data["node"], "calibration": calib_dict}
        res_repr = yaml.dump(out_dict, default_flow_style=False)
        if cal_file is None:
            cal_file = meas_file.stem + "_cal.yml"

        if cal_file.exists():
            ValueError(f"Calibration File already exists ({cal_file})")
        with open(cal_file, "w") as f:
            f.write(res_repr)
        return cal_file
