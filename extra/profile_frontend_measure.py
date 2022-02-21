#!/usr/bin/env python3
'''

This program verifies a proper function of the shepherd frontends for emulator and harvester.
- a SMU is used to step through various voltage and current combinations
- runs from 0 to 5 V and 0 to 50 mA with about 600 combinations
- pru also samples 1 s of data (100k datapoints) from ADCs
- this tracking allows to show influence of design-changes
- "profile_frontend_plot.py" can be used to analyse the data

'''
import itertools
import time
from pathlib import Path
from keithley2600b import SMU
import click
import zerorpc
import sys
import numpy as np
from fabric import Connection
import msgpack
import msgpack_numpy

script_path = Path(__file__).parent
shepherd_path = script_path.parent.joinpath('software', 'python-package', 'shepherd').resolve()
sys.path.append(str(shepherd_path))
import calibration_default as cal_def


# SMU Config-Parameters
mode_4wire = True
pwrline_cycles = 16  # .001 to 25 allowed, >= 20 SMU throws sporadic errors (timeouts)


adict = {"voltage_shp_V": 0,
         "voltage_shp_raw": 1,
         "voltage_ref_V": 2,
         "current_shp_A": 3,
         "current_shp_raw": 4,
         "current_ref_A" : 5,
         }

INSTR_EMU = """
---------------------- Characterize Shepherd-Frontend -----------------------
- remove targets from target-ports
- remove harvesting source from harvester-input (P6)
- Connect SMU channel A Lo to P10-1 (Target-A GND)
- Connect SMU channel A Hi to P10-2 (Target-A Voltage)
- Resistor (~200 Ohm) and Cap (1-10 uF) between 
    - P11-1 (Target-B GND)
    - P11-2 (Target-B Voltage)
- Connect SMU channel B Lo to P6-2 (HRV-Input GND)
- Connect SMU channel B Hi to P6-3 & -4 (VSense and VHarvest connected together)
- NOTE: be sure to use 4-Wire-Cabling to SMU for improved results (can be disabled in script)
"""


def meas_emulator_setpoint(rpc_client, smu_channel, voltage_V, current_A):
    voltage_V = min(max(voltage_V, 0.0), 5.0)

    if smu_channel is not None:
        current_A = min(max(current_A, 0.0), 0.050)
        smu_channel.configure_isource(range=0.050)
        smu_channel.set_current(-current_A, vlimit=5.0)  # negative current, because smu acts as a drain
        smu_channel.set_output(True)

    # write both dac-channels of emulator
    dac_voltage_raw = rpc_client.convert_value_to_raw("emulator", "dac_voltage_b", voltage_V)
    rpc_client.set_aux_target_voltage_raw((2 ** 20) + dac_voltage_raw, also_main=True)
    adc_data = rpc_client.sample_from_pru(10)
    adc_currents_raw = msgpack.unpackb(adc_data, object_hook=msgpack_numpy.decode)[0]
    adc_current_raw = float(np.mean(adc_currents_raw))

    # voltage measurement only for information
    if smu_channel is not None:
        smu_voltage = smu_channel.measure_voltage(nplc=pwrline_cycles)
    else:
        smu_voltage = voltage_V
        current_A = rpc_client.convert_raw_to_value("emulator", "adc_current", adc_current_raw)

    print(f"  SMU-reference: {1000*current_A:.3f} mA @ {smu_voltage:.4f} V; "
          f"  emu-c-raw: mean={adc_current_raw:.2f}, stddev={np.std(adc_currents_raw):.2f} "
          f"@ {voltage_V:.3f} V")

    if smu_channel is not None:
        smu_channel.set_output(False)
    return adc_currents_raw, smu_voltage, current_A


# TODO: the two meas-FNs could be the same if pru would fill
def meas_harvester_setpoint(rpc_client, smu_channel, voltage_V, current_A):
    voltage_V = min(max(voltage_V, 0.0), 5.0)
    current_A = min(max(current_A, 0.0), 0.050)

    smu_channel.configure_isource(range=0.050)
    smu_channel.set_current(current_A, vlimit=5.0)  # negative current, because smu acts as a drain
    smu_channel.set_output(True)

    # write both dac-channels of emulator
    dac_voltage_raw = rpc_client.convert_value_to_raw("harvester", "dac_voltage_b", voltage_V)
    rpc_client.set_aux_target_voltage_raw((2 ** 20) + dac_voltage_raw, also_main=True)
    adc_data = rpc_client.sample_from_pru(10)
    adc_currents_raw = msgpack.unpackb(adc_data, object_hook=msgpack_numpy.decode)[0]
    adc_current_raw = float(np.mean(adc_currents_raw))
    adc_voltages_raw = msgpack.unpackb(adc_data, object_hook=msgpack_numpy.decode)[1]
    adc_voltage_raw = float(np.mean(adc_voltages_raw))
    voltage_adc_V = rpc_client.convert_raw_to_value("harvester", "adc_voltage", adc_voltage_raw)

    smu_voltage = smu_channel.measure_voltage(nplc=pwrline_cycles)

    print(f"  SMU-reference: {1000*current_A:.3f} mA @ {smu_voltage:.4f} V;"
          f"  hrv-c-raw: mean={adc_current_raw:.2f}, stddev={np.std(adc_currents_raw):.2f};"
          f"  hrv-v-raw: mean={adc_voltage_raw:.2f}, stddev={np.std(adc_voltages_raw):.2f}"
          f" ({voltage_adc_V:.3f} V);   DAC: {voltage_V:.3f} V")

    smu_channel.set_output(False)
    return adc_currents_raw, adc_voltages_raw, smu_voltage, current_A


@click.group(context_settings=dict(help_option_names=["-h", "--help"], obj={}))
def cli():
    pass


@cli.command()
@click.argument("host", type=str)
@click.option("--user", "-u", type=str, default="joe", help="Host Username")
@click.option("--password", "-p", type=str, default=None, help="Host User Password -> only needed when key-credentials are missing")
@click.option("--outfile", "-o", type=click.Path(), help="save file, if no filename is provided the hostname will be used")
@click.option("--smu-ip", type=str, default="192.168.1.108")
@click.option("--harvester", "-h", is_flag=True, help="handle harvester")
@click.option("--emulator", "-e", is_flag=True, help="handle emulator")
@click.option("--short", "-s", is_flag=True, help="reduce voltage / current steps for faster profiling (2x faster)")
def measure(host, user, password, outfile, smu_ip, harvester, emulator, short):

    if password is not None:
        fabric_args = {"password": password}
    else:
        fabric_args = {}

    rpc_client = zerorpc.Client(timeout=60, heartbeat=20)
    time_now = time.time()

    if not any([harvester, emulator]):
        harvester = True
        emulator = True
    components = ("_emu" if emulator else "") + ("_hrv" if harvester else "")

    with SMU.ethernet_device(smu_ip) as smu, Connection(host, user=user, connect_kwargs=fabric_args) as cnx:
        cnx.sudo("systemctl restart shepherd-rpc", hide=True, warn=True)
        #time.sleep(4)
        rpc_client.connect(f"tcp://{ host }:4242")
        smu.A.configure_4port_mode(mode_4wire)
        smu.B.configure_4port_mode(mode_4wire)
        if short:
            file_path = Path(outfile).stem + "_profile_short" + components + ".npz"
            voltages_V = np.append([5.0, 0.05], np.arange(0.0, 5.1, .4))
            currents_A = [0e-6, 1e-6, 2e-6, 5e-6, 10e-6, 50e-6,
                          100e-6, 500e-6, 1e-3, 5e-3, 10e-3,
                          15e-3, 20e-3, 25e-3, 30e-3, 35e-3, 40e-3, 45e-3, 50e-3]
        else:
            file_path = Path(outfile).stem + "_profile_full" + components + ".npz"
            voltages_V = np.append([0.05], np.arange(0.0, 5.1, .2))
            currents_A = [0e-6, 1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6,
                          100e-6, 200e-6, 500e-6, 1e-3, 2e-3, 5e-3, 10e-3,
                          15e-3, 20e-3, 25e-3, 30e-3, 35e-3, 40e-3, 45e-3, 50e-3]
        voltages_res_V = np.append([0.05], np.arange(0.0, 5.1, .1))

        results_a = results_b = results_h = None

        click.echo(INSTR_EMU)
        print(f" -> Profiler will sweep through {len(voltages_V)} voltages and {len(currents_A)} currents")
        usr_conf1 = click.confirm("Confirm that everything is set up ...")

        if usr_conf1 and harvester:
            print(f"Measurement - Harvester - Voltage & Current")
            if True:  # TODO: test if leakage is fixed
                rpc_client.switch_shepherd_mode("hrv_adc_read")
                rpc_client.set_aux_target_voltage_raw((2 ** 20) + 0, also_main=True)
                rpc_client.set_shepherd_pcb_power(False)
                time.sleep(2)
                rpc_client.set_shepherd_pcb_power(True)
            rpc_client.switch_shepherd_mode("hrv_adc_read")
            results_h = np.zeros([6, len(voltages_V) * len(currents_A)], dtype=object)
            for index, (voltage, current) in enumerate(itertools.product(voltages_V, currents_A)):
                cdata, vdata, v_meas, c_set = meas_harvester_setpoint(rpc_client, smu.B, voltage, current)
                results_h[0][index] = voltage
                results_h[1][index] = vdata
                results_h[2][index] = v_meas
                results_h[3][index] = current
                results_h[4][index] = cdata
                results_h[5][index] = c_set
            rpc_client.set_aux_target_voltage_raw((2 ** 20) + cal_def.dac_voltage_to_raw(5.0), also_main=True)

        if usr_conf1 and emulator:
            print(f"Measurement - Emulator - Current - ADC Channel A - Target A")
            rpc_client.switch_shepherd_mode("emu_adc_read")
            results_a = np.zeros([6, len(voltages_V) * len(currents_A)], dtype=object)
            rpc_client.select_target_for_power_tracking(True)  # targetA-Port will get the monitored dac-channel-b
            for index, (voltage, current) in enumerate(itertools.product(voltages_V, currents_A)):
                cdata, v_meas, c_set = meas_emulator_setpoint(rpc_client, smu.A, voltage, current)
                results_a[0][index] = voltage
                results_a[1][index] = rpc_client.convert_value_to_raw("emulator", "dac_voltage_b", voltage)
                results_a[2][index] = v_meas
                results_a[3][index] = current
                results_a[4][index] = cdata
                results_a[5][index] = c_set

        # TODO: currently channel-switch does not work, can be removed with future HW
        if usr_conf1 and emulator and click.confirm("Confirm that everything is set up for Part 2 (Port B) ..."):
            print(f"Measurement - Emulator - Current - ADC Channel A - Target B")
            rpc_client.switch_shepherd_mode("emu_adc_read")
            results_b = np.zeros([6, len(voltages_res_V)], dtype=object)
            rpc_client.select_target_for_power_tracking(False)  # targetB-Port will get the monitored dac-channel-b
            for index, voltage in enumerate(voltages_res_V):
                cdata, v_meas, c_shp = meas_emulator_setpoint(rpc_client, None, voltage, None)
                results_b[0][index] = voltage
                results_b[1][index] = rpc_client.convert_value_to_raw("emulator", "dac_voltage_b", voltage)
                results_b[2][index] = v_meas  # is equal to "voltage"-var
                results_b[3][index] = c_shp
                results_b[4][index] = cdata
                results_b[5][index] = c_shp

        if usr_conf1:
            np.savez_compressed(file_path, emu_a=results_a, emu_b=results_b, hrv=results_h)
            cnx.sudo("systemctl stop shepherd-rpc", hide=True, warn=True)
        print(f"Profiling took {(time.time() - time_now):.1f} s")


if __name__ == "__main__":
    cli()
