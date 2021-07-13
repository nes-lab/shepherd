#!/usr/bin/env python3
import time
from keithley2600b import SMU
import click
import zerorpc
import sys
import yaml
import numpy as np
import tempfile
from scipy import stats
from fabric import Connection
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression

V_REF_DAC = 2.5
G_DAC_A = 1.0
G_DAC_V = 2.0
M_DAC = 16

INSTR_HRVST = """
---------- Harvesting calibration -------------
- Short P6-3 and P6-4 (Current Sink and Voltage-Measurement of Harvest-Port)
- Connect SMU Channel A/B Lo to GND (P6-2, P8-1/2)
- Connect SMU Channel A Hi to P6-1 (SimBuf)
- Connect SMU Channel B Hi to P6-3/4

WARNING: old Code - not for new v2-Capes

"""

INSTR_EMU = """
---------------------- Emulation calibration -----------------------
- remove targets from target-ports
- Connect SMU channel A Lo to P10-1 (Target-A GND)
- Connect SMU channel A Hi to P10-2 (Target-A Voltage)
- Connect SMU channel B Lo to P11-1 (Target-B GND)
- Connect SMU channel B Hi to P11-2 (Target-B Voltage)

"""


def convert_dac_voltage_to_raw(value_V: float) -> int:
    return int((value_V * (2 ** M_DAC)) / (G_DAC_V * V_REF_DAC))


def measurements_to_calibration(measurements):

    calib_dict = dict()

    for component in ["harvesting", "emulation"]:
        calib_dict[component] = dict()
        for channel in ["dac_voltage_a", "dac_voltage_b", "adc_current", "adc_voltage"]:
            calib_dict[component][channel] = dict()
            try:
                sample_points = measurements[component][channel]
            except KeyError:
                calib_dict[component][channel]["gain"] = float(1.0)
                calib_dict[component][channel]["offset"] = float(0.0)
                print(f"NOTE: skipping '{component} - {channel}', because no data was found")
                continue
            x = np.empty(len(sample_points))
            y = np.empty(len(sample_points))
            for i, point in enumerate(sample_points):
                x[i] = point["shepherd_raw"]
                y[i] = point["reference_si"]
            WLS = LinearRegression()
            WLS.fit(x.reshape(-1, 1), y.reshape(-1, 1), sample_weight=1.0 / x)
            intercept = WLS.intercept_
            slope = WLS.coef_[0]
            calib_dict[component][channel]["gain"] = float(slope)
            calib_dict[component][channel]["offset"] = float(intercept)
    return calib_dict


def measure_current(rpc_client, smu_channel, adc_channel):

    values = [0.00001, 0.0001, 0.001, 0.01, 0.02, 0.04]
    rpc_client.dac_write("current", 0)
    rpc_client.dac_write("voltage", 0)

    smu_channel.configure_isource(range=0.05)
    results = list()
    for val in values:
        smu_channel.set_current(val, vlimit=3.0)
        smu_channel.set_output(True)
        time.sleep(0.25)

        meas = np.empty(10)
        for i in range(10):
            meas[i] = rpc_client.adc_read(adc_channel)
        meas_avg = float(np.mean(meas))
        results.append({"reference_si": val, "shepherd_raw": meas_avg})
        print(f"ref: {val*1000:.4f}mA meas: {meas_avg}")

        smu_channel.set_output(False)

    return results


def measure_voltage(rpc_client, smu_channel, adc_channel):

    values = [0.1, 0.5, 1.0, 1.5, 2.0, 2.5]
    rpc_client.dac_write("current", 0)
    rpc_client.dac_write("voltage", 0)

    smu_channel.configure_vsource(range=4.0)
    results = list()
    for val in values:
        smu_channel.set_voltage(val, ilimit=0.05)
        smu_channel.set_output(True)
        time.sleep(0.25)
        meas = np.empty(10)
        for i in range(10):
            meas[i] = rpc_client.adc_read(adc_channel)

        meas_avg = float(np.mean(meas))
        results.append({"reference_si": val, "shepherd_raw": meas_avg})
        print(f"ref: {val}V meas: {meas_avg}")

        smu_channel.set_output(False)
    return results


def meas_emulator_current(rpc_client, smu_channel):

    currents_A = [0.0, 1e-6, 1e-5, 1e-4, 1e-3, 2e-3, 4e-3, 6e-3, 8e-3, 10e-3]

    # write both dac-channels of emulator
    dac_voltage = 2.5
    print(f" -> setting dac-voltage to {dac_voltage} V")
    rpc_client.dac_write(0b1100, convert_dac_voltage_to_raw(dac_voltage))

    smu_channel.configure_isource(range=0.050)
    smu_channel.set_current(0.000, vlimit=3.0)
    smu_channel.set_output(True)

    results = list()
    for current_A in currents_A:
        smu_channel.set_current(-current_A, vlimit=3.0)  # negative current, because smu acts as a drain

        time.sleep(0.25)

        adc_current_raw = rpc_client.adc_read("emu")
        # voltage measurement only for information, drop might appear severe, because 4port-measurement is not active
        smu_voltage = smu_channel.measure_voltage(range=5.0, nplc=1.0)

        results.append({"reference_si": current_A, "shepherd_raw": adc_current_raw})
        print(f"  reference: {current_A} A @ {smu_voltage:.4f} V; shepherd: {adc_current_raw} raw")

    smu_channel.set_output(False)
    return results


def meas_emulator_voltage(rpc_client, smu_channel):

    voltages = np.linspace(0.3, 2.5, 12)

    values = [convert_dac_voltage_to_raw(val) for val in voltages]

    # write both dac-channels of emulator
    rpc_client.dac_write(0b1100, 0)

    smu_channel.configure_isource(range=0.001)
    smu_channel.set_current(0.0005, vlimit=5.0)
    smu_channel.set_output(True)

    results = list()
    for iter, val in enumerate(values):
        rpc_client.dac_write(0b1100, val)

        time.sleep(0.5)

        meas = smu_channel.measure_voltage(range=5.0, nplc=1.0)

        results.append({"reference_si": meas, "shepherd_raw": val})
        print(f"  shepherd: {voltages[iter]:.3f} V ({val} raw); reference: {meas} V")

    smu_channel.set_output(False)
    return results


def measurement_dynamic(values: list, dict_val: str = "shepherd_raw") -> float:
    value_min = min([value[dict_val] for value in values])
    value_max = max([value[dict_val] for value in values])
    return (value_max / value_min)


@click.group(context_settings=dict(help_option_names=["-h", "--help"], obj={}))
def cli():
    pass


@cli.command()
@click.argument("host", type=str)
@click.option("--user", "-u", type=str, default="joe", help="Host Username")
@click.option("--password", "-p", type=str, default=None, help="Host User Password -> only needed when key-credentials are missing")
@click.option("--outfile", "-o", type=click.Path(), help="save file, if no filename is provided the hostname will be used")
@click.option("--smu-ip", type=str, default="192.168.1.108")
@click.option("--all", "all_", is_flag=True)
@click.option("--harvesting", is_flag=True)
@click.option("--emulation", is_flag=True)
def measure(host, user, password, outfile, smu_ip, all_, harvesting, emulation):

    if all_:
        if harvesting or emulation:
            raise click.UsageError("Either provide --all or individual flags")

        harvesting = True
        emulation = True
    if not any([all_, harvesting, emulation]):
        harvesting = True
        emulation = True

    if password is not None:
        fabric_args = {"password": password}
    else:
        fabric_args = {}

    rpc_client = zerorpc.Client(timeout=60, heartbeat=20)
    measurement_dict = dict()

    with SMU.ethernet_device(smu_ip) as smu, Connection(host, user=user, connect_kwargs=fabric_args) as cnx:
        # TODO: enable 4 Port Mode if possible
        res = cnx.sudo("systemctl restart shepherd-rpc", hide=True, warn=True)
        #time.sleep(4)
        rpc_client.connect(f"tcp://{ host }:4242")

        if harvesting:
            click.echo(INSTR_HRVST)
            usr_conf = click.confirm("Confirm that everything is set up ...")
            if usr_conf:
                measurement_dict["harvesting"] = {
                    "voltage": list(),
                    "current": list(),
                }
                rpc_client.set_harvester(True)
                measurement_dict["harvesting"]["current"] = measure_current(
                    rpc_client, smu.B, "A_IN"
                )
                measurement_dict["harvesting"]["voltage"] = measure_voltage(
                    rpc_client, smu.B, "V_IN"
                )
                rpc_client.set_harvester(False)

        if emulation:
            click.echo(INSTR_EMU)
            usr_conf = click.confirm("Confirm that everything is set up ...")
            if usr_conf:
                measurement_dict["emulation"] = {
                    "dac_voltage_a": list(),
                    "dac_voltage_b": list(),
                    "adc_current": list(),
                    "adc_voltage": list(),  # not existing currently
                }

                # TODO: hw-rev2.1r0 has switched channels, this code unswitches if needed
                print(f"Measurement - Emulation - Current - ADC Channel A - Target A")
                # targetA-Port will get the monitored dac-channel-b
                rpc_client.select_target_for_power_tracking(True)
                meas_a = meas_emulator_current(rpc_client, smu.A)
                meas_b = meas_emulator_current(rpc_client, smu.B)
                if measurement_dynamic(meas_a) > measurement_dynamic(meas_b):
                    measurement_dict["emulation"]["adc_current"] = meas_a
                else:
                    measurement_dict["emulation"]["adc_current"] = meas_b

                print(f"Measurement - Emulation - Current - ADC Channel A - Target B")
                # targetB-Port will get the monitored dac-channel-b
                rpc_client.select_target_for_power_tracking(False)
                meas_a = meas_emulator_current(rpc_client, smu.A)
                meas_b = meas_emulator_current(rpc_client, smu.B)
                if measurement_dynamic(meas_a) > measurement_dynamic(meas_b):
                    measurement_dict["emulation"]["adc_voltage"] = meas_a
                else:
                    measurement_dict["emulation"]["adc_voltage"] = meas_b

                print(f"Measurement - Emulation - Voltage - DAC Channel A")
                measurement_dict["emulation"]["dac_voltage_a"] = meas_emulator_voltage(rpc_client, smu.A)
                print(f"Measurement - Emulation - Voltage - DAC Channel B")
                measurement_dict["emulation"]["dac_voltage_b"] = meas_emulator_voltage(rpc_client, smu.B)

        out_dict = {"node": host, "measurements": measurement_dict}
        res = cnx.sudo("systemctl stop shepherd-rpc", hide=True, warn=True)
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
