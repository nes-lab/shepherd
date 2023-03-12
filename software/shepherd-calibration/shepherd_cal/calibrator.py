#!/usr/bin/env python3
import time
from pathlib import Path
from typing import Dict
from typing import Optional
from typing import Union

import msgpack
import msgpack_numpy
import numpy as np
import yaml
import zerorpc
from fabric import Connection
from keithley2600 import Keithley2600
from keithley2600.keithley_driver import Keithley2600Base
from keithley2600.keithley_driver import KeithleyClass

from shepherd.calibration import CalibrationData
from shepherd.calibration_default import dac_voltage_to_raw

from .calibration_plot import plot_calibration
from .logger import logger

INSTR_CAL_HRV = """
---------------------- Harvester calibration -----------------------
- Short P6-2 and P6-4
    - P6-2 -> VSense / Voltage-Measurement of Harvest-Port
    - P6-4 -> VHarv / Current Sink of Harvest-Port
- Connect SMU Channel A & B Lo to GND (P6-1, alternatively P8-1/2)
- Connect SMU Channel A Hi to P6-3 (VSim)
- Connect SMU Channel B Hi to P6-2/4 (VSense, VHarv -> connected together)
"""

INSTR_CAL_EMU = """
---------------------- Emulator calibration -----------------------
- remove targets from target-ports
- Connect SMU channel A Lo to P10-1 (Target-Port A GND)
- Connect SMU channel A Hi to P10-2 (Target-Port A Voltage)
- Connect SMU channel B Lo to P11-1 (Target-Port B GND)
- Connect SMU channel B Hi to P11-2 (Target-Port B Voltage)
"""

INSTR_4WIRE = "- NOTE: be sure to use 4-Wire-Cabling to SMU for improved results"


class Calibrator:
    def __init__(
        self,
        host: str,
        user: str,
        password: Optional[str] = None,
        smu_ip: Optional[str] = None,
        mode_4wire: bool = True,
        pwrline_cycles: float = 16,
    ):
        fabric_args: Dict[str, str] = {}
        if password is not None:
            fabric_args["password"] = password

        self._mode_4wire: bool = mode_4wire
        self._pwrline_cycles: float = min(max(pwrline_cycles, 0.001), 25)

        self._host: str = host
        self.sheep: zerorpc.Client = zerorpc.Client(timeout=60, heartbeat=20)
        self._cnx: Connection = Connection(host, user=user, connect_kwargs=fabric_args)
        # TODO: check connection or else .sudo below throws socket.gaierror when sheep unavail

        if smu_ip is None:
            raise ValueError("Please provide an IP for the SMU")

        self.kth: Keithley2600Base = Keithley2600(f"TCPIP0::{smu_ip}::INSTR")

        # enter
        self._cnx.sudo("systemctl restart shepherd-rpc", hide=True, warn=True)
        time.sleep(2)
        self.sheep.connect(f"tcp://{host}:4242")
        if self.kth is not None:
            self.kth.reset()

    def __del__(self):
        # ... overcautious
        self._cnx.sudo("systemctl stop shepherd-rpc", hide=True, warn=True)
        self._cnx.close()
        del self._cnx

    def set_smu_auto_on(self, smu: KeithleyClass) -> None:
        smu.source.output = smu.OUTPUT_ON
        smu.measure.autozero = smu.AUTOZERO_AUTO
        smu.measure.autorangev = smu.AUTORANGE_ON
        smu.measure.autorangei = smu.AUTORANGE_ON
        smu.measure.nplc = self._pwrline_cycles

    def set_smu_to_vsource(
        self,
        smu: KeithleyClass,
        value_v: float,
        limit_i: float,
    ) -> float:
        value_v = min(max(value_v, 0.0), 5.0)
        limit_i = min(max(limit_i, -0.050), 0.050)
        smu.sense = smu.SENSE_REMOTE if self._mode_4wire else smu.SENSE_LOCAL
        smu.source.levelv = value_v
        smu.source.limiti = limit_i
        smu.source.func = smu.OUTPUT_DCVOLTS
        smu.source.autorangev = smu.AUTORANGE_ON
        self.set_smu_auto_on(smu)
        return value_v

    def set_smu_to_isource(
        self,
        smu: KeithleyClass,
        value_i: float,
        limit_v: float = 5.0,
    ) -> float:
        value_i = min(max(value_i, -0.050), 0.050)
        limit_v = min(max(limit_v, 0.0), 5.0)
        smu.sense = smu.SENSE_REMOTE if self._mode_4wire else smu.SENSE_LOCAL
        smu.source.leveli = value_i
        smu.source.limitv = limit_v
        smu.source.func = smu.OUTPUT_DCAMPS
        smu.source.autorangei = smu.AUTORANGE_ON
        self.set_smu_auto_on(smu)
        return value_i

    @staticmethod
    def reject_outliers(data: np.ndarray, m: float = 2.0):
        d = np.abs(data - np.median(data))
        mdev = np.median(d)
        s = d / mdev if mdev else 0.0
        return data[s < m]

    def measure_harvester_adc_voltage(self, smu: KeithleyClass) -> list:
        smu_current_A = 0.1e-3
        smu_voltages_V = np.linspace(0.3, 2.5, 12)
        dac_voltage_V = 4.5
        dac_voltage_raw = dac_voltage_to_raw(dac_voltage_V)

        mode_old = self.sheep.switch_shepherd_mode("hrv_adc_read")
        logger.debug(
            " -> setting dac-voltage to %s V (raw = %s) -> upper limit now max",
            dac_voltage_V,
            dac_voltage_raw,
        )
        self.sheep.set_aux_target_voltage_raw(
            (2**20) + dac_voltage_raw,
            also_main=True,
        )

        self.set_smu_to_vsource(smu, 0.0, smu_current_A)

        results = []
        for voltage_V in smu_voltages_V:
            smu.source.levelv = voltage_V
            time.sleep(0.5)
            self.sheep.sample_from_pru(2)  # flush previous buffers (just to be safe)

            meas_enc = self.sheep.sample_from_pru(40)  # captures # buffers
            meas_rec = msgpack.unpackb(meas_enc, object_hook=msgpack_numpy.decode)
            adc_current_raw = float(np.mean(self.reject_outliers(meas_rec[0])))

            adc_filtered = self.reject_outliers(meas_rec[1])
            outlier_rate = 100 * (1 - adc_filtered.size / meas_rec[1].size)
            adc_voltage_raw = float(np.mean(adc_filtered))

            smu_current_mA = 1000 * smu.measure.i()

            results.append(
                {"reference_si": float(voltage_V), "shepherd_raw": adc_voltage_raw},
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
        self.sheep.switch_shepherd_mode(mode_old)
        return results

    def measure_harvester_adc_current(
        self,
        smu: KeithleyClass,
    ) -> list:  # TODO: combine with previous FN
        sm_currents_A = [10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3]
        dac_voltage_V = 2.5
        dac_voltage_raw = dac_voltage_to_raw(dac_voltage_V)

        mode_old = self.sheep.switch_shepherd_mode("hrv_adc_read")
        logger.debug(
            " -> setting dac-voltage to %s V (raw = %s)",
            dac_voltage_V,
            dac_voltage_raw,
        )
        self.sheep.set_aux_target_voltage_raw(
            (2**20) + dac_voltage_raw,
            also_main=True,
        )

        self.set_smu_to_isource(smu, 0.0, 3.0)

        results = []
        for current_A in sm_currents_A:
            smu.source.leveli = current_A
            time.sleep(0.5)
            self.sheep.sample_from_pru(2)  # flush previous buffers (just to be safe)

            meas_enc = self.sheep.sample_from_pru(40)  # captures # buffers
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
        self.sheep.switch_shepherd_mode(mode_old)
        return results

    def measure_emulator_current(self, smu: KeithleyClass) -> list:
        sm_currents_A = [10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3]
        dac_voltage_V = 2.5

        mode_old = self.sheep.switch_shepherd_mode("emu_adc_read")
        logger.debug(" -> setting dac-voltage to %s V", dac_voltage_V)
        # write both dac-channels of emulator
        self.sheep.set_aux_target_voltage_raw(
            (2**20) + dac_voltage_to_raw(dac_voltage_V),
            also_main=True,
        )  # TODO: rpc seems to have trouble with named parameters, so 2**20 is a bugfix

        self.set_smu_to_isource(smu, 0.0, 3.0)

        results = []
        for current_A in sm_currents_A:
            smu.source.leveli = (
                -current_A
            )  # negative current, because smu acts as a drain
            time.sleep(0.5)
            self.sheep.sample_from_pru(2)  # flush previous buffers (just to be safe)

            meas_enc = self.sheep.sample_from_pru(40)  # captures # buffers
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
        self.sheep.switch_shepherd_mode(mode_old)
        return results

    def measure_dac_voltage(
        self,
        smu: KeithleyClass,
        dac_bitmask: int,
        drain: bool = False,
    ) -> list:
        smu_current_A = 0.1e-3
        if drain:  # for emulator
            smu_current_A = -smu_current_A
        voltages_V = np.linspace(0.3, 2.5, 12)

        voltages_raw = [dac_voltage_to_raw(val) for val in voltages_V]

        # write both dac-channels of emulator
        self.sheep.dac_write(dac_bitmask, 0)

        self.set_smu_to_isource(smu, smu_current_A, 5.0)

        results = []
        for _iter, _val in enumerate(voltages_raw):
            self.sheep.dac_write(dac_bitmask, _val)
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
        results["adc_voltage"] = self.measure_harvester_adc_voltage(self.kth.smub)

        logger.info("Measurement - Harvester - ADC . Current")
        results["adc_current"] = self.measure_harvester_adc_current(self.kth.smub)

        logger.info("Measurement - Harvester - DAC . Voltage - Channel A (VSim)")
        results["dac_voltage_a"] = self.measure_dac_voltage(self.kth.smua, 0b0001)

        logger.info("Measurement - Harvester - DAC . Voltage - Channel B (VHarv)")
        results["dac_voltage_b"] = self.measure_dac_voltage(self.kth.smub, 0b0010)
        return results

    def measure_emulator(self) -> dict:
        results = {}
        logger.info("Measurement - Emulator - ADC . Current - Target A")
        # targetA-Port will get the monitored dac-channel-b
        self.sheep.select_target_for_power_tracking(True)
        results["adc_current"] = self.measure_emulator_current(self.kth.smua)

        logger.info("Measurement - Emulator - ADC . Current - Target B")
        # targetB-Port will get the monitored dac-channel-b
        self.sheep.select_target_for_power_tracking(False)
        # NOTE: adc_voltage does not exist for emulator, but gets used for target port B
        results["adc_voltage"] = self.measure_emulator_current(self.kth.smub)

        self.sheep.select_target_for_power_tracking(
            False,
        )  # routes DAC.A to TGT.A to SMU-A
        logger.info("Measurement - Emulator - DAC . Voltage - Channel A")
        results["dac_voltage_a"] = self.measure_dac_voltage(
            self.kth.smua,
            0b1100,
            drain=True,
        )

        logger.info("Measurement - Emulator - DAC . Voltage - Channel B")
        results["dac_voltage_b"] = self.measure_dac_voltage(
            self.kth.smub,
            0b1100,
            drain=True,
        )
        return results

    def write(
        self,
        cal_file: Union[str, Path],
        serial: str,
        version: str,
        cal_date: str,
    ):
        temp_file = "/tmp/calib.yml"  # noqa: S108
        if isinstance(cal_file, str):
            cal_file = Path(cal_file)
        with open(cal_file) as stream:
            content = yaml.safe_load(stream)
            cal_std = content.get("node", "unknown")
            cal_host = content.get("host", cal_std)
        if cal_host != self._host:
            logger.warning(
                "Calibration data for '%s' doesn't match host '%s'.",
                cal_host,
                self._host,
            )

        self._cnx.put(cal_file, temp_file)  # noqa: S108
        logger.info("----------EEPROM WRITE------------")
        result = self._cnx.sudo(
            f"shepherd-sheep -vvv eeprom write -v {version} -s {serial} -d {cal_date}"
            f" -c {temp_file}",
            warn=True,
            hide=True,
        )
        logger.info(result.stdout)
        logger.info("---------------------------------")

    def read(self):
        logger.info("----------EEPROM READ------------")
        result = self._cnx.sudo("shepherd-sheep -vvv eeprom read", warn=True, hide=True)
        logger.info(result.stdout)
        logger.info("---------------------------------")

    def retrieve(self, cal_file: str):
        temp_file = "/tmp/calib.yml"  # noqa: S108
        result = self._cnx.sudo(
            f"shepherd-sheep -vvv eeprom read -c {temp_file}",
            warn=True,
            hide=True,
        )
        logger.info(result.stdout)
        self._cnx.get(temp_file, local=str(cal_file))

    @staticmethod
    def convert(
        meas_file: Path,
        cal_file: Optional[Path] = None,
        do_plot: bool = False,
    ) -> Path:
        if not isinstance(meas_file, Path):
            meas_file = Path(meas_file)
        with open(meas_file) as stream:
            meas_data = yaml.safe_load(stream)
            meas_dict = meas_data["measurements"]

        calib_dict = CalibrationData.from_measurements(meas_file).data

        if do_plot:
            plot_calibration(meas_dict, calib_dict, meas_file)

        out_dict = {"node": meas_data["node"], "calibration": calib_dict}
        res_repr = yaml.dump(out_dict, default_flow_style=False)
        if cal_file is None:
            cal_file = Path(meas_file.stem + "_cal.yml")
        if not isinstance(cal_file, Path):
            cal_file = Path(cal_file)

        if cal_file.exists():
            raise ValueError(f"Calibration File already exists ({cal_file})")
        with open(cal_file, "w") as f:
            f.write(res_repr)
        return cal_file
