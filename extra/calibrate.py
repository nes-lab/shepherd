#!/usr/bin/env python3
import time
from pathlib import Path

from keithley2600b import SMU
# TODO: changes to lib
# - VMeas - allow self._inst.write(f"smu{ self._name }.sense = 1") # 4Wire-Mode
''' significant changes with 90cm 1mm² cabling
from
  smu-reference: 0.0001 A @ 1.0004 V
  smu-reference: 0.0003 A @ 1.0005 V
  smu-reference: 0.001 A @ 1.0007 V
  smu-reference: 0.003 A @ 1.0016 V
  smu-reference: 0.01 A @ 1.0045 V
to
  smu-reference: 0.0003 A @ 1.0003 V
  smu-reference: 0.001 A @ 1.0003 V
  smu-reference: 0.003 A @ 1.0003 V
  smu-reference: 0.01 A @ 1.0004 V
'''
import click
import zerorpc
import yaml
import numpy as np
import tempfile
from fabric import Connection
from sklearn.linear_model import LinearRegression
import msgpack
import msgpack_numpy

INSTR_HRVST = """
---------------------- Harvester calibration -----------------------
- Short P6-3 and P6-4 (Current Sink and Voltage-Measurement of Harvest-Port)
- Connect SMU Channel A/B Lo to GND (P6-2, P8-1/2)
- Connect SMU Channel A Hi to P6-1 (SimBuf)
- Connect SMU Channel B Hi to P6-3/4

"""

INSTR_EMU = """
---------------------- Emulator calibration -----------------------
- remove targets from target-ports
- Connect SMU channel A Lo to P10-1 (Target-Port A GND)
- Connect SMU channel A Hi to P10-2 (Target-Port A Voltage)
- Connect SMU channel B Lo to P11-1 (Target-Port B GND)
- Connect SMU channel B Hi to P11-2 (Target-Port B Voltage)

"""

# TODO: next 25 lines are copied from calibration_default.py

V_REF_DAC = 2.5  # [V]
G_DAC = 2.0  # [gain / V_REF]
M_DAC = 16  # [bit]

V_REF_ADC = 4.096  # [V]
G_ADC = 1.25  # [gain / V_REF]
M_ADC = 18  # [bit]

R_SHT = 2.0  # [ohm]
G_INST_AMP = 48  # [n]


def adc_current_to_raw(current: float) -> int:
    v_adc = G_INST_AMP * R_SHT * current
    return int(v_adc * (2 ** M_ADC) / (G_ADC * V_REF_ADC))


def adc_voltage_to_raw(voltage: float) -> int:
    return int(voltage * (2 ** M_ADC) / (G_ADC * V_REF_ADC))


def dac_voltage_to_raw(value_V: float) -> int:
    return int((value_V * (2 ** M_DAC)) / (G_DAC * V_REF_DAC))


def measurements_to_calibration(measurements):

    calib_dict = dict()

    for component in ["harvester", "emulator"]:
        calib_dict[component] = dict()
        for channel in ["dac_voltage_a", "dac_voltage_b", "adc_current", "adc_voltage"]:
            calib_dict[component][channel] = dict()
            if "dac_voltage" in channel:
                slope = 1.0 / dac_voltage_to_raw(1.0)
            elif "adc_current" in channel:
                slope = 1.0 / adc_current_to_raw(1.0)
            elif "adc_voltage" in channel:
                slope = 1.0 / adc_voltage_to_raw(1.0)
            else:
                slope = 1.0
            intercept = 0
            try:
                sample_points = measurements[component][channel]
                x = np.empty(len(sample_points))
                y = np.empty(len(sample_points))
                for i, point in enumerate(sample_points):
                    x[i] = point["shepherd_raw"]
                    y[i] = point["reference_si"]
                WLS = LinearRegression()
                WLS.fit(x.reshape(-1, 1), y.reshape(-1, 1), sample_weight=1.0 / x)
                intercept = WLS.intercept_
                slope = WLS.coef_[0]
            except KeyError:
                print(f"NOTE: data was not found -> replacing '{component} - {channel}' with default values (gain={slope})")
            except ValueError as e:
                print(f"NOTE: data was faulty -> replacing '{component} - {channel}' with default values (gain={slope}) [{e}]")

            calib_dict[component][channel]["gain"] = float(slope)
            calib_dict[component][channel]["offset"] = float(intercept)
    return calib_dict


def meas_harvester_adc_voltage(rpc_client, smu_channel):

    smu_current_A = 0.1e-3
    smu_voltages_V = np.linspace(0.3, 2.5, 12)
    dac_voltage_V = 4.5
    dac_voltage_raw = dac_voltage_to_raw(dac_voltage_V)

    mode_old = rpc_client.switch_shepherd_mode("hrv_adc_read")
    print(f" -> setting dac-voltage to {dac_voltage_V} V (raw = {dac_voltage_raw}) -> upper limit now max")
    rpc_client.set_aux_target_voltage_raw(2 ** 20 + dac_voltage_raw, also_main=True)

    smu_channel.configure_vsource(range=5)
    smu_channel.set_voltage(0.0, ilimit=smu_current_A)
    smu_channel.set_output(True)
    results = list()
    for voltage_V in smu_voltages_V:
        smu_channel.set_voltage(voltage_V, ilimit=smu_current_A)
        time.sleep(0.5)
        rpc_client.sample_from_pru(2)  # flush previous buffers (just to be safe)

        meas_enc = rpc_client.sample_from_pru(40)  # captures # buffers
        meas_rec = msgpack.unpackb(meas_enc, object_hook=msgpack_numpy.decode)
        adc_voltage_raw = float(np.mean(meas_rec[1]))
        adc_current_raw = float(np.mean(meas_rec[0]))
        adc_voltage_med = float(np.median(meas_rec[1]))
        smu_current_mA = 1000 * smu_channel.measure_current(range=smu_current_A, nplc=10)

        results.append({"reference_si": float(voltage_V), "shepherd_raw": adc_voltage_raw})
        print(f"  SMU-reference: {voltage_V:.3f} V @ {smu_current_mA:.4f} mA;"
              f"  shepherd: {adc_voltage_raw:.4f} raw ({adc_voltage_med:.4f} median); current: {adc_current_raw} raw")

    smu_channel.set_output(False)
    rpc_client.switch_shepherd_mode(mode_old)
    return results


def meas_harvester_adc_current(rpc_client, smu_channel):  # TODO: combine with previous FN

    sm_currents_A = [10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3]
    dac_voltage_V = 2.5
    dac_voltage_raw = dac_voltage_to_raw(dac_voltage_V)

    mode_old = rpc_client.switch_shepherd_mode("hrv_adc_read")
    print(f" -> setting dac-voltage to {dac_voltage_V} V (raw = {dac_voltage_raw})")
    rpc_client.set_aux_target_voltage_raw(2 ** 20 + dac_voltage_raw, also_main=True)

    smu_channel.configure_isource(range=0.050)
    smu_channel.set_current(0.000, vlimit=3.0)
    smu_channel.set_output(True)
    results = list()
    for current_A in sm_currents_A:
        smu_channel.set_current(current_A, vlimit=3.0)
        time.sleep(0.5)
        rpc_client.sample_from_pru(2)  # flush previous buffers (just to be safe)

        meas_enc = rpc_client.sample_from_pru(40)  # captures # buffers
        meas_rec = msgpack.unpackb(meas_enc, object_hook=msgpack_numpy.decode)
        adc_current_raw = float(np.mean(meas_rec[0]))
        adc_current_med = float(np.median(meas_rec[0]))

        # voltage measurement only for information, drop might appear severe, because 4port-measurement is not active
        smu_voltage = smu_channel.measure_voltage(range=5.0, nplc=10)

        results.append({"reference_si": current_A, "shepherd_raw": adc_current_raw})
        print(f"  SMU-reference: {1000*current_A:.4f} mA @ {smu_voltage:.4f} V;"
              f"  shepherd: {adc_current_raw:.4f} raw ({adc_current_med:.4f} median)")

    smu_channel.set_output(False)
    rpc_client.switch_shepherd_mode(mode_old)
    return results


def meas_emulator_current(rpc_client, smu_channel):

    sm_currents_A = [0.1e-3, 0.3e-3, 1e-3, 3e-3, 10e-3]
    dac_voltage_V = 2.5

    mode_old = rpc_client.switch_shepherd_mode("emu_adc_read")
    print(f" -> setting dac-voltage to {dac_voltage_V} V")
    # write both dac-channels of emulator
    rpc_client.set_aux_target_voltage_raw(dac_voltage_to_raw(dac_voltage_V), also_main=True)

    smu_channel.configure_isource(range=0.050)
    smu_channel.set_current(0.000, vlimit=3.0)
    smu_channel.set_output(True)
    results = list()
    for current_A in sm_currents_A:
        smu_channel.set_current(-current_A, vlimit=3.0)  # negative current, because smu acts as a drain
        time.sleep(0.5)
        rpc_client.sample_from_pru(2)  # flush previous buffers (just to be safe)

        meas_enc = rpc_client.sample_from_pru(40)  # captures # buffers
        meas_rec = msgpack.unpackb(meas_enc, object_hook=msgpack_numpy.decode)
        adc_current_raw = float(np.mean(meas_rec[0]))
        adc_current_med = float(np.median(meas_rec[0]))

        # voltage measurement only for information, drop might appear severe, because 4port-measurement is not active
        smu_voltage = smu_channel.measure_voltage(range=5.0, nplc=10)

        results.append({"reference_si": current_A, "shepherd_raw": adc_current_raw})
        print(f"  SMU-reference: {1000*current_A:.4f} mA @ {smu_voltage:.4f} V;"
              f"  shepherd: {adc_current_raw:.4f} raw ({adc_current_med:.4f} median)")

    smu_channel.set_output(False)
    rpc_client.switch_shepherd_mode(mode_old)
    return results


def meas_dac_voltage(rpc_client, smu_channel, dac_bitmask):

    smu_current_A = 0.0005
    voltages_V = np.linspace(0.3, 2.5, 12)

    voltages_raw = [dac_voltage_to_raw(val) for val in voltages_V]

    # write both dac-channels of emulator
    rpc_client.dac_write(dac_bitmask, 0)

    smu_channel.configure_isource(range=0.001)
    smu_channel.set_current(smu_current_A, vlimit=5.0)
    smu_channel.set_output(True)

    results = list()
    for _iter, _val in enumerate(voltages_raw):
        rpc_client.dac_write(dac_bitmask, _val)
        time.sleep(0.5)
        smu_channel.measure_voltage(range=5.0, nplc=10)
        meas_series = list([])
        for index in range(30):
            meas_series.append(smu_channel.measure_voltage(range=5.0, nplc=10))
            time.sleep(0.01)
        mean = float(np.mean(meas_series))
        medi = float(np.median(meas_series))
        smu_current_mA = 1000 * smu_channel.measure_current(range=0.01, nplc=10)

        results.append({"reference_si": mean, "shepherd_raw": _val})
        print(f"  shepherd: {voltages_V[_iter]:.3f} V ({_val:0f} raw);"
              f"  SMU-reference: {mean:.6f} V; median: {medi:.6f} V; current: {smu_current_mA:.3f} mA")

    smu_channel.set_output(False)
    return results


def measurement_dynamic(values: list, dict_val: str = "shepherd_raw") -> float:
    value_min = min([value[dict_val] for value in values])
    value_max = max([value[dict_val] for value in values])
    return value_max - value_min


@click.group(context_settings=dict(help_option_names=["-h", "--help"], obj={}))
def cli():
    pass


@cli.command()
@click.argument("host", type=str)
@click.option("--user", "-u", type=str, default="joe", help="Host Username")
@click.option("--password", "-p", type=str, default=None, help="Host User Password -> only needed when key-credentials are missing")
@click.option("--outfile", "-o", type=click.Path(), help="save-file, file gets extended if it already exists")
@click.option("--smu-ip", type=str, default="192.168.1.108")
@click.option("--all", "all_", is_flag=True, help="handle both, harvester and emulator")
@click.option("--harvester", is_flag=True, help="handle only harvester")
@click.option("--emulator", is_flag=True, help="handle only emulator")
def measure(host, user, password, outfile, smu_ip, all_, harvester, emulator):

    if all_:
        if harvester or emulator:
            raise click.UsageError("Either provide --all or individual flags")

        harvester = True
        emulator = True
    if not any([all_, harvester, emulator]):
        harvester = True
        emulator = True

    if password is not None:
        fabric_args = {"password": password}
    else:
        fabric_args = {}

    rpc_client = zerorpc.Client(timeout=60, heartbeat=20)

    measurement_dict = dict()
    if (outfile is not None) and Path(outfile).exists():
        with open(outfile, "r") as config_data:
            config = yaml.safe_load(config_data)
            if "measurements" in config:
                measurement_dict = config["measurements"]
                print("Save-File loaded successfully - will extend dataset")

    with SMU.ethernet_device(smu_ip) as smu, Connection(host, user=user, connect_kwargs=fabric_args) as cnx:
        # TODO: enable 4 Port Mode if possible
        res = cnx.sudo("systemctl restart shepherd-rpc", hide=True, warn=True)
        rpc_client.connect(f"tcp://{ host }:4242")

        if harvester:
            click.echo(INSTR_HRVST)
            usr_conf = click.confirm("Confirm that everything is set up ...")
            if usr_conf:
                measurement_dict["harvester"] = dict()
                print(f"Measurement - Harvester - ADC . Voltage")
                measurement_dict["harvester"]["adc_voltage"] = meas_harvester_adc_voltage(rpc_client, smu.B)
                print(f"Measurement - Harvester - ADC . Current")
                measurement_dict["harvester"]["adc_current"] = meas_harvester_adc_current(rpc_client, smu.B)
                print(f"Measurement - Harvester - DAC . Voltage - Channel A (VSim)")
                measurement_dict["harvester"]["dac_voltage_a"] = meas_dac_voltage(rpc_client, smu.A, 0b0001)
                print(f"Measurement - Harvester - DAC . Voltage - Channel B (VHarv)")
                measurement_dict["harvester"]["dac_voltage_b"] = meas_dac_voltage(rpc_client, smu.B, 0b0010)

        if emulator:
            click.echo(INSTR_EMU)
            usr_conf = click.confirm("Confirm that everything is set up ...")
            if usr_conf:
                measurement_dict["emulator"] = {
                    "dac_voltage_a": list(),
                    "dac_voltage_b": list(),
                    "adc_current": list(),
                    "adc_voltage": list(),  # not existing currently
                }

                print(f"Measurement - Emulator - ADC . Current - Target A")
                # targetA-Port will get the monitored dac-channel-b
                rpc_client.select_target_for_power_tracking(True)
                meas_a = meas_emulator_current(rpc_client, smu.A)
                meas_b = meas_emulator_current(rpc_client, smu.B)
                if measurement_dynamic(meas_a) > measurement_dynamic(meas_b):
                    measurement_dict["emulator"]["adc_current"] = meas_a
                else:
                    measurement_dict["emulator"]["adc_current"] = meas_b

                print(f"Measurement - Emulator - ADC . Current - Target B")
                # targetB-Port will get the monitored dac-channel-b
                rpc_client.select_target_for_power_tracking(False)
                meas_a = meas_emulator_current(rpc_client, smu.A)
                meas_b = meas_emulator_current(rpc_client, smu.B)
                if measurement_dynamic(meas_a) > measurement_dynamic(meas_b):
                    measurement_dict["emulator"]["adc_voltage"] = meas_a
                else:
                    measurement_dict["emulator"]["adc_voltage"] = meas_b

                rpc_client.select_target_for_power_tracking(False)  # routes DAC.A to TGT.A to SMU.A
                print(f"Measurement - Emulator - DAC . Voltage - Channel A")
                measurement_dict["emulator"]["dac_voltage_a"] = meas_dac_voltage(rpc_client, smu.A, 0b1100)
                print(f"Measurement - Emulator - DAC . Voltage - Channel B")
                measurement_dict["emulator"]["dac_voltage_b"] = meas_dac_voltage(rpc_client, smu.B, 0b1100)

        out_dict = {"node": host, "measurements": measurement_dict}
        cnx.sudo("systemctl stop shepherd-rpc", hide=True, warn=True)
        res_repr = yaml.dump(out_dict, default_flow_style=False)
        if outfile is not None:
            with open(outfile, "w") as f:
                f.write(res_repr)
        else:
            print(res_repr)


@cli.command()
@click.argument("infile", type=click.Path(exists=True))
@click.option("--outfile", "-o", type=click.Path())
def convert(infile, outfile):
    with open(infile, "r") as stream:
        in_data = yaml.safe_load(stream)
    measurement_dict = in_data["measurements"]

    calib_dict = measurements_to_calibration(measurement_dict)

    out_dict = {"node": in_data["node"], "calibration": calib_dict}
    res_repr = yaml.dump(out_dict, default_flow_style=False)
    if outfile is not None:
        with open(outfile, "w") as f:
            f.write(res_repr)
    else:
        print(res_repr)


@cli.command()
@click.argument("host", type=str)
@click.option("--calibfile", "-c", type=click.Path(exists=True))
@click.option("--measurementfile", "-m", type=click.Path(exists=True))
@click.option("--version", "-v", type=str, default="22A0",
    help="Cape version number, 4 Char, e.g. 22A0, reflecting hardware revision")
@click.option("--serial_number", "-s", type=str, required=True,
    help="Cape serial number, 12 Char, e.g. 2021w28i0001, reflecting year, week of year, increment")
@click.option("--user", "-u", type=str, default="joe")
@click.option("--password", "-p", type=str, default=None, help="Host User Password -> only needed when key-credentials are missing")
def write(host, calibfile, measurementfile, version, serial_number, user, password):

    if calibfile is None:
        if measurementfile is None:
            raise click.UsageError(
                "provide one of calibfile or measurementfile"
            )

        with open(measurementfile, "r") as stream:
            in_measurements = yaml.safe_load(stream)
        measurement_dict = in_measurements["measurements"]
        in_data = dict()
        in_data["calibration"] = measurements_to_calibration(measurement_dict)
        in_data["node"] = in_measurements["node"]
        res_repr = yaml.dump(in_data, default_flow_style=False)
        tmp_file = tempfile.NamedTemporaryFile()
        calibfile = tmp_file.name
        with open(calibfile, "w") as f:
            f.write(res_repr)

    else:
        if measurementfile is not None:
            raise click.UsageError(
                "provide only one of calibfile or measurementfile"
            )
        with open(calibfile, "r") as stream:
            in_data = yaml.safe_load(stream)

    if in_data["node"] != host:
        click.confirm(
            (
                f"Calibration data for '{ in_data['node'] }' doesn't match "
                f"host '{ host }'. Do you wish to proceed?"
            ),
            abort=True,
        )

    if password is not None:
        fabric_args = {"password": password}
    else:
        fabric_args = {}

    with Connection(host, user=user, connect_kwargs=fabric_args) as cnx:
        cnx.put(calibfile, "/tmp/calib.yml")
        cnx.sudo(
            (
                f"shepherd-sheep eeprom write -v { version } -s {serial_number}"
                " -c /tmp/calib.yml"
            )
        )
        click.echo("----------EEPROM READ------------")
        cnx.sudo("shepherd-sheep eeprom read")
        click.echo("---------------------------------")


@cli.command()
@click.argument("host", type=str)
@click.option("--user", "-u", type=str, default="joe")
@click.option("--password", "-p", type=str, default=None, help="Host User Password -> only needed when key-credentials are missing")
def read(host, user, password):

    if password is not None:
        fabric_args = {"password": password}
    else:
        fabric_args = {}

    with Connection(host, user=user, connect_kwargs=fabric_args) as cnx:
        click.echo("----------EEPROM READ------------")
        cnx.sudo("shepherd-sheep eeprom read")
        click.echo("---------------------------------")


if __name__ == "__main__":
    cli()
