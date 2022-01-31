#!/usr/bin/env python3
import time
from pathlib import Path

from keithley2600b import SMU
import click
import zerorpc
import yaml
import numpy as np
import tempfile
from fabric import Connection
import msgpack
import msgpack_numpy
import matplotlib.pyplot as plt
import sys

script_path = Path(__file__).parent
shepherd_path = script_path.parent.joinpath('software', 'python-package', 'shepherd').resolve()
sys.path.append(str(shepherd_path))

from calibration import CalibrationData
from calibration_default import *

# SMU Config-Parameters
mode_4wire = True
pwrline_cycles = 10

INSTR_HRVST = """
---------------------- Harvester calibration -----------------------
- Short P6-3 and P6-4 (Current Sink and Voltage-Measurement of Harvest-Port)
- Connect SMU Channel A/B Lo to GND (P6-2, P8-1/2)
- Connect SMU Channel A Hi to P6-1 (SimBuf)
- Connect SMU Channel B Hi to P6-3/4
- NOTE: be sure to use 4-Wire-Cabling to SMU for improved results
"""

INSTR_EMU = """
---------------------- Emulator calibration -----------------------
- remove targets from target-ports
- Connect SMU channel A Lo to P10-1 (Target-Port A GND)
- Connect SMU channel A Hi to P10-2 (Target-Port A Voltage)
- Connect SMU channel B Lo to P11-1 (Target-Port B GND)
- Connect SMU channel B Hi to P11-2 (Target-Port B Voltage)
- NOTE: be sure to use 4-Wire-Cabling to SMU for improved results
"""


def plot_calibration(measurements, calibration, file_name):
    for component in ["harvester", "emulator"]:
        for channel in ["dac_voltage_a", "dac_voltage_b", "adc_current", "adc_voltage"]:
            try:
                sample_points = measurements[component][channel]
                xp = np.empty(len(sample_points))
                yp = np.empty(len(sample_points))
                for i, point in enumerate(sample_points):
                    xp[i] = point["shepherd_raw"]
                    yp[i] = point["reference_si"]
                gain = calibration[component][channel]["gain"]
                offset = calibration[component][channel]["offset"]
                xl = [xp[0], xp[-1]]
                yl = [gain * xlp + offset for xlp in xl]
            except KeyError:
                print(f"NOTE: data was not found - will skip plot")
                continue
            except ValueError as e:
                print(f"NOTE: data was faulty - will skip plot [{e}]")
                continue

            fig, ax = plt.subplots()
            ax.plot(xl, yl, ":", linewidth=2, color='green')
            ax.scatter(xp, yp, marker='*', color='k')
            ax.set_xlabel(r'raw value', fontsize=10)
            ax.set_ylabel(r'SI-Unit', fontsize=10)
            ax.set_title(f'Calibration-Check for {component} - {channel}')
            ax.grid(True)
            fig.set_figwidth(11)
            fig.set_figheight(10)
            fig.tight_layout()
            plt.savefig(Path(file_name).stem + f"_{component}_{channel}.png")
            plt.close(fig)
            plt.clf()


def meas_harvester_adc_voltage(rpc_client, smu_channel):

    smu_current_A = 0.1e-3
    smu_voltages_V = np.linspace(0.3, 2.5, 12)
    dac_voltage_V = 4.5
    dac_voltage_raw = dac_voltage_to_raw(dac_voltage_V)

    mode_old = rpc_client.switch_shepherd_mode("hrv_adc_read")
    print(f" -> setting dac-voltage to {dac_voltage_V} V (raw = {dac_voltage_raw}) -> upper limit now max")
    rpc_client.set_aux_target_voltage_raw((2 ** 20) + dac_voltage_raw, also_main=True)

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
        adc_current_raw = float(np.mean(meas_rec[0]))
        adc_voltage_raw = float(np.mean(meas_rec[1]))
        adc_voltage_med = float(np.median(meas_rec[1]))
        smu_current_mA = 1000 * smu_channel.measure_current(range=smu_current_A, nplc=pwrline_cycles)

        results.append({"reference_si": float(voltage_V), "shepherd_raw": adc_voltage_raw})
        print(f"  SMU-reference: {voltage_V:.3f} V @ {smu_current_mA:.3f} mA;"
              f"  shepherd: {adc_voltage_raw:.4f} raw (median = {adc_voltage_med:.0f}); current: {adc_current_raw} raw")

    smu_channel.set_output(False)
    rpc_client.switch_shepherd_mode(mode_old)
    return results


def meas_harvester_adc_current(rpc_client, smu_channel):  # TODO: combine with previous FN

    sm_currents_A = [10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3]
    dac_voltage_V = 2.5
    dac_voltage_raw = dac_voltage_to_raw(dac_voltage_V)

    mode_old = rpc_client.switch_shepherd_mode("hrv_adc_read")
    print(f" -> setting dac-voltage to {dac_voltage_V} V (raw = {dac_voltage_raw})")
    rpc_client.set_aux_target_voltage_raw((2 ** 20) + dac_voltage_raw, also_main=True)

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
        smu_voltage = smu_channel.measure_voltage(range=5.0, nplc=pwrline_cycles)

        results.append({"reference_si": current_A, "shepherd_raw": adc_current_raw})
        print(f"  SMU-reference: {1000*current_A:.3f} mA @ {smu_voltage:.4f} V;"
              f"  shepherd: {adc_current_raw:.4f} raw (median = {adc_current_med:.0f})")

    smu_channel.set_output(False)
    rpc_client.switch_shepherd_mode(mode_old)
    return results


def meas_emulator_current(rpc_client, smu_channel):

    sm_currents_A = [10e-6, 30e-6, 100e-6, 300e-6, 1e-3, 3e-3, 10e-3]
    dac_voltage_V = 2.5

    mode_old = rpc_client.switch_shepherd_mode("emu_adc_read")
    print(f" -> setting dac-voltage to {dac_voltage_V} V")
    # write both dac-channels of emulator
    rpc_client.set_aux_target_voltage_raw((2 ** 20) + dac_voltage_to_raw(dac_voltage_V), also_main=True)  # TODO: rpc seems to have trouble with named parameters, so 2**20 is a bugfix

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
        smu_voltage = smu_channel.measure_voltage(range=5.0, nplc=pwrline_cycles)

        results.append({"reference_si": current_A, "shepherd_raw": adc_current_raw})
        print(f"  SMU-reference: {1000*current_A:.3f} mA @ {smu_voltage:.4f} V;"
              f"  shepherd: {adc_current_raw:.4f} raw (median = {adc_current_med:.0f})")

    smu_channel.set_output(False)
    rpc_client.switch_shepherd_mode(mode_old)
    return results


def meas_dac_voltage(rpc_client, smu_channel, dac_bitmask):

    smu_current_A = 0.1e-3
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
        smu_channel.measure_voltage(range=5.0, nplc=pwrline_cycles)
        meas_series = list([])
        for index in range(30):
            meas_series.append(smu_channel.measure_voltage(range=5.0, nplc=pwrline_cycles))
            time.sleep(0.01)
        mean = float(np.mean(meas_series))
        medi = float(np.median(meas_series))
        smu_current_mA = 1000 * smu_channel.measure_current(range=0.01, nplc=pwrline_cycles)

        results.append({"reference_si": mean, "shepherd_raw": _val})
        print(f"  shepherd: {voltages_V[_iter]:.3f} V ({_val:.0f} raw);"
              f"  SMU-reference: {mean:.6f} V (median = {medi:.6f}); current: {smu_current_mA:.3f} mA")

    smu_channel.set_output(False)
    return results


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
        cnx.sudo("systemctl restart shepherd-rpc", hide=True, warn=True)
        rpc_client.connect(f"tcp://{ host }:4242")
        smu.A.configure_4port_mode(mode_4wire)
        smu.B.configure_4port_mode(mode_4wire)

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
                measurement_dict["emulator"] = dict()

                print(f"Measurement - Emulator - ADC . Current - Target A")
                # targetA-Port will get the monitored dac-channel-b
                rpc_client.select_target_for_power_tracking(True)
                measurement_dict["emulator"]["adc_current"] = meas_emulator_current(rpc_client, smu.A)

                print(f"Measurement - Emulator - ADC . Current - Target B")
                # targetB-Port will get the monitored dac-channel-b
                rpc_client.select_target_for_power_tracking(False)
                # NOTE: adc_voltage does not exist for emulator, but gets used for target port B
                measurement_dict["emulator"]["adc_voltage"] = meas_emulator_current(rpc_client, smu.B)

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
@click.option("--plot", "-p", is_flag=True, help="generate plots that contain data points and calibration model")
def convert(infile, outfile, plot: bool):
    with open(infile, "r") as stream:
        meas_data = yaml.safe_load(stream)
        meas_dict = meas_data["measurements"]

    calib_dict = CalibrationData.from_measurements(infile).data

    if plot:
        plot_calibration(meas_dict, calib_dict, infile)

    out_dict = {"node": meas_data["node"], "calibration": calib_dict}
    res_repr = yaml.dump(out_dict, default_flow_style=False)
    if outfile is not None:
        with open(outfile, "w") as f:
            f.write(res_repr)
    else:
        print(res_repr)


@cli.command()
@click.argument("host", type=str)
@click.option("--calfile", "-c", type=click.Path(exists=True))
@click.option("--measurementfile", "-m", type=click.Path(exists=True))
@click.option("--version", "-v", type=str, default="22A0",
              help="Cape version number, 4 Char, e.g. 22A0, reflecting hardware revision")
@click.option("--serial_number", "-s", type=str, required=True,
              help="Cape serial number, 12 Char, e.g. 2021w28i0001, reflecting year, week of year, increment")
@click.option("--user", "-u", type=str, default="joe")
@click.option("--password", "-p", type=str, default=None, help="Host User Password -> only needed when key-credentials are missing")
def write(host, calfile, measurementfile, version, serial_number, user, password):

    if calfile is None:
        if measurementfile is None:
            raise click.UsageError(
                "provide one of cal-file or measurement-file"
            )

        with open(measurementfile, "r") as stream:
            in_measurements = yaml.safe_load(stream)
        in_data = dict()
        in_data["calibration"] = CalibrationData.from_measurements(measurementfile).data
        in_data["node"] = in_measurements["node"]
        res_repr = yaml.dump(in_data, default_flow_style=False)
        tmp_file = tempfile.NamedTemporaryFile()
        calfile = tmp_file.name
        with open(calfile, "w") as f:
            f.write(res_repr)

    else:
        if measurementfile is not None:
            raise click.UsageError(
                "provide only one of cal-file or measurement-file"
            )
        with open(calfile, "r") as stream:
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
        cnx.put(calfile, "/tmp/calib.yml")
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
