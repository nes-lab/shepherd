#!/usr/bin/env python3
import itertools
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
import msgpack
import msgpack_numpy

V_REF_DAC = 2.5
G_DAC_A = 1.0
G_DAC_V = 2.0
M_DAC = 16

adict = {"voltage_shp_V": 0,
         "voltage_shp_raw": 1,
         "voltage_ref_V": 2,
         "current_shp_A": 3,
         "current_shp_raw": 4,
         "current_ref_A" : 5,
         }

INSTR_EMU = """
---------------------- Characterize Emulator-Frontend -----------------------
- remove targets from target-ports
- Connect SMU channel A Lo to P10-1 (Target-A GND)
- Connect SMU channel A Hi to P10-2 (Target-A Voltage)
- Resistor (~200 Ohm) and Cap (1-10 uF) between 
    - P11-1 (Target-B GND)
    - P11-2 (Target-B Voltage)

"""


def convert_dac_voltage_to_raw(value_V: float) -> int:
    return int((value_V * (2 ** M_DAC)) / (G_DAC_V * V_REF_DAC))


def meas_emulator_setpoint(rpc_client, smu_channel, voltage_V, current_A):
    voltage_V = min(max(voltage_V, 0.0), 5.0)
    current_A = min(max(current_A, 0.0), 0.050)

    smu_channel.configure_isource(range=0.050)
    smu_channel.set_current(-current_A, vlimit=5.0)  # negative current, because smu acts as a drain
    smu_channel.set_output(True)

    # write both dac-channels of emulator
    rpc_client.set_aux_target_voltage_raw(convert_dac_voltage_to_raw(voltage_V), also_main=True)
    time.sleep(0.2)
    rpc_client.sample_from_pru(3)  # seems to solve some readout-errors at start
    meas_enc = rpc_client.sample_from_pru(10)
    meas_rec = msgpack.unpackb(meas_enc, object_hook=msgpack_numpy.decode)
    adc_current_raw = float(np.mean(meas_rec[0]))

    # voltage measurement only for information, drop might appear severe, because 4port-measurement is not active
    smu_voltage = smu_channel.measure_voltage(range=5.0, nplc=1.0)

    print(f"  reference: {current_A} A @ {smu_voltage:.4f} V; shepherd: "
          f"mean={adc_current_raw:.2f}, "
          f"[{np.min(meas_rec)}, {np.max(meas_rec)}], "
          f"stddev={np.std(meas_rec):.2f} "
          f"@ {voltage_V} V")

    smu_channel.set_output(False)
    return meas_rec, smu_voltage, current_A


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
@click.option("--outfile", "-o", type=click.Path(), help="save file, if no filename is provided the hostname will be used")
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

    if harvester:
        raise click.UsageError("Currently not implemented")

    with SMU.ethernet_device(smu_ip) as smu, Connection(host, user=user, connect_kwargs=fabric_args) as cnx:
        # TODO: enable 4 Port Mode if possible
        res = cnx.sudo("systemctl restart shepherd-rpc", hide=True, warn=True)
        #time.sleep(4)
        rpc_client.connect(f"tcp://{ host }:4242")

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

                mode_old = rpc_client.switch_shepherd_mode("emu_adc_read")

                print(f"Measurement - Emulator - Current - ADC Channel A - Target A")
                voltages_V = [0.0, 0.05, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
                currents_A = [0e-3, 1e-6, 5e-6, 10e-6, 50e-6, 100e-6, 500e-6,
                              1e-3, 5e-3, 10e-3, 15e-3, 20e-3, 25e-3,
                              30e-3, 35e-3, 40e-3, 45e-3]
                rpc_client.select_target_for_power_tracking(True) # targetA-Port will get the monitored dac-channel-b
                results_a = np.zeros([6, len(voltages_V) * len(currents_A)], dtype=object)
                for index, (current, voltage) in enumerate(itertools.product(currents_A, voltages_V)):
                    cdata, v_meas, c_set = meas_emulator_setpoint(rpc_client, smu.A, voltage, current)
                    results_a[0][index] = voltage
                    results_a[1][index] = convert_dac_voltage_to_raw(voltage)
                    results_a[2][index] = v_meas
                    results_a[3][index] = current
                    results_a[4][index] = cdata
                    results_a[5][index] = c_set

                print(f"Measurement - Emulator - Current - ADC Channel A - Target B")
                voltages_V = np.linspace(0.0, 4.5, 46)
                currents_A = [20e-3]
                rpc_client.select_target_for_power_tracking(False) # targetB-Port will get the monitored dac-channel-b
                results_b = np.zeros([6, len(voltages_V) * len(currents_A)], dtype=object)
                for index, (current, voltage) in enumerate(itertools.product(currents_A, voltages_V)):
                    cdata, v_meas, c_set = meas_emulator_setpoint(rpc_client, smu.B, voltage, current)
                    results_b[0][index] = voltage
                    results_b[1][index] = convert_dac_voltage_to_raw(voltage)
                    results_b[2][index] = v_meas
                    results_b[3][index] = current
                    results_b[4][index] = cdata
                    results_b[5][index] = c_set

                np.savez_compressed("profile_emu_channels.npz", a=results_a, b=results_b)
                rpc_client.switch_shepherd_mode(mode_old)


if __name__ == "__main__":
    cli()
