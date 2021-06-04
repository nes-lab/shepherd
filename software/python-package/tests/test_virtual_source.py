import pytest
import subprocess
import time
from pathlib import Path

from shepherd import ShepherdDebug, CalibrationData
from shepherd.virtual_source import VirtualSource

@pytest.fixture()
def debug_shepherd(request, shepherd_up, mode):
    cal = CalibrationData.from_default()
    vss = "./example_virtsource_settings.yml"
    deb = ShepherdDebug()
    request.addfinalizer(deb.__del__)
    deb.__enter__()
    request.addfinalizer(deb.__exit__)
    deb.vsource_init(vss, cal)
    return deb


@pytest.fixture
def py_vsource():
    cal = CalibrationData.from_default()
    vss = "./example_virtsource_settings.yml"
    vvs = VirtualSource(vss, cal)
    return vss

@pytest.fixture
def reference_vss():
    vss = dict()
    # keep in sync with "example_virtsource_settings.yml"
    vss["C_storage_F"] = 1 * (10 ** -3)
    vss["V_storage_V"] = 3.5
    vss["t_sample_s"] = 10 * (10 ** -6)
    vss["eta_in"] = 0.5
    vss["eta_out"] = 0.8
    vss["I_storage_leak_A"] = 9 * (10 ** -9)
    vss["V_storage_disable_threshold_V"] = 2.3
    vss["V_out_V"] = 2.0

@pytest.mark.hardware
def vsource_add_charge(debug_shepherd: ShepherdDebug, py_vsource: VirtualSource, reference_vss):
    # set desired end-voltage of storage-cap:
    V_cap_V = 4.000
    dt_s = 0.100
    V_inp_V = 1.0
    dV_cap_V = V_cap_V - reference_vss["V_storage_V"]
    I_cIn = dV_cap_V * reference_vss["C_storage_F"] / dt_s
    P_inp_W = I_cIn * reference_vss["V_storage_V"] / reference_vss["eta_in"]
    I_inp_sample = P_inp_W / V_inp_V
    n_samples = dt_s / reference_vss["t_sample_s"]

    for iter in range(n_samples):
        v_inp_uV = int(V_inp_V * 10 ** 6)
        i_inp_nA = int(I_inp_sample * 10 ** 9)
        debug_shepherd.vsource_calc_inp_power(i_inp_nA, v_inp_uV)
        debug_shepherd.vsource_update_capacitor()
        py_vsource.calc_inp_power(i_inp_nA, v_inp_uV)
        py_vsource.update_capacitor()

    debug_shepherd.vsource_calc_inp_power(0, 0)
    V_cap_pru_V = float(debug_shepherd.vsource_update_capacitor()) * 10**-6
    py_vsource.calc_inp_power(0, 0)
    V_cap_py_V = float(py_vsource.update_capacitor()) * 10**-6

    deviation_pru = 100*abs(V_cap_pru_V/V_cap_V - 1)
    deviation_py = 100*abs(V_cap_py_V/V_cap_V - 1)
    print(f"VCap goal = {V_cap_V} V, py = {V_cap_py_V} V (dev={deviation_py} %), pru = {V_cap_pru_V} V (dev={deviation_pru} %)")
    assert deviation_py < 1.0
    assert deviation_pru < 2.0

@pytest.mark.hardware
def vsource_drain_charge(debug_shepherd: ShepherdDebug, py_vsource: VirtualSource, reference_vss):
    # set desired end-voltage of storage-cap - low enough to disable output
    V_cap_V = 2.200
    dt_s = 5.00

    dV_cap_V = V_cap_V - reference_vss["V_storage_V"]
    I_cOut = - dV_cap_V * reference_vss["C_storage_F"] / dt_s - reference_vss["I_storage_leak_A"]
    P_out_W = I_cOut * reference_vss["V_storage_V"] * reference_vss["eta_out"]
    I_out_sample = P_out_W / reference_vss["V_out_V"]

    cal = CalibrationData.from_default()
    I_out_adc_raw = cal.convert_value_to_raw("emulation", "adc_current", I_out_sample)
    n_samples = dt_s / reference_vss["t_sample_s"]

    for iter in range(n_samples):
        debug_shepherd.vsource_calc_out_power(I_out_adc_raw)
        debug_shepherd.vsource_update_capacitor()
        debug_shepherd.vsource_update_buckboost()

        py_vsource.calc_out_power(I_out_adc_raw)
        py_vsource.update_capacitor()
        py_vsource.update_buckboost()

    debug_shepherd.vsource_calc_out_power(0)
    V_cap_pru_V = float(debug_shepherd.vsource_update_capacitor()) * 10**-6
    V_out_pru_raw = debug_shepherd.vsource_update_buckboost()
    py_vsource.calc_out_power(0)
    V_cap_py_V = float(py_vsource.update_capacitor()) * 10**-6
    V_out_py_raw = py_vsource.update_buckboost()

    deviation_pru = 100*abs(V_cap_pru_V/reference_vss["V_storage_disable_threshold_V"] - 1)
    deviation_py = 100*abs(V_cap_py_V/reference_vss["V_storage_disable_threshold_V"] - 1)
    print(f"VCap goal = {V_cap_V} V, py = {V_cap_py_V} V (dev={deviation_py} %), pru = {V_cap_pru_V} V (dev={deviation_pru} %)")
    print(f"VOut goal = 0 n, py = {V_out_py_raw} n, pru = {V_out_pru_raw} n")
    assert deviation_py < 1.0
    assert deviation_pru < 2.0
    assert V_out_pru_raw < 1
    assert V_out_py_raw < 1
