import pytest
import subprocess
import time
from pathlib import Path

from shepherd import ShepherdDebug, CalibrationData
from shepherd.virtual_source import VirtualSource


@pytest.fixture()
def debug_shepherd(request, shepherd_up):
    cal = CalibrationData.from_default()
    here = Path(__file__).absolute()
    vss = here.parent / "./example_virtsource_settings.yml"
    deb = ShepherdDebug()
    request.addfinalizer(deb.__del__)
    deb.__enter__()
    request.addfinalizer(deb.__exit__)
    deb.vsource_init(vss, cal)
    return deb


@pytest.fixture
def py_vsource():
    cal = CalibrationData.from_default()
    here = Path(__file__).absolute()
    vss = here.parent / "./example_virtsource_settings.yml"
    return VirtualSource(vss, cal)


@pytest.fixture
def reference_vss():
    vss = dict()
    # keep in sync with "example_virtsource_settings.yml"
    vss["C_storage_F"] = 100 * (10 ** -6)
    vss["V_storage_V"] = 3.0
    vss["t_sample_s"] = 10 * (10 ** -6)
    vss["eta_in"] = 0.5
    vss["eta_out"] = 0.8
    vss["I_storage_leak_A"] = 9 * (10 ** -9)
    vss["V_storage_disable_threshold_V"] = 2.3
    vss["V_out_V"] = 2.0
    return vss


@pytest.mark.hardware
def test_vsource_add_charge(debug_shepherd: ShepherdDebug, py_vsource: VirtualSource, reference_vss):
    # set desired end-voltage of storage-cap:
    V_cap_V = 3.500
    dt_s = 0.100
    V_inp_V = 1.0
    dV_cap_V = V_cap_V - reference_vss["V_storage_V"]
    I_cIn = dV_cap_V * reference_vss["C_storage_F"] / dt_s
    P_inp_W = I_cIn * reference_vss["V_storage_V"] / reference_vss["eta_in"]
    I_inp_A = P_inp_W / V_inp_V
    # prepare fn-parameters
    v_inp_uV = int(V_inp_V * 10 ** 6)
    i_inp_nA = int(I_inp_A * 10 ** 9)
    n_samples = int(dt_s / reference_vss["t_sample_s"])
    print(f"CHARGE - feeding I = {I_inp_A} A, V = {V_inp_V} V into vSource with {n_samples} steps")
    print(f" PRU VCap = {debug_shepherd.vsource_update_capacitor()} uV")
    print(f" PRU PInp = {debug_shepherd.vsource_calc_inp_power(v_inp_uV, i_inp_nA)} fW")
    print(f" Py  VCap = {py_vsource.update_capacitor()} uV")
    print(f" Py  PInp = {py_vsource.calc_inp_power(v_inp_uV, i_inp_nA)} fW")

    for iter in range(n_samples):
        debug_shepherd.vsource_charge(v_inp_uV, i_inp_nA)  # combines P_in, P_out, V_cap, state_update
        py_vsource.calc_inp_power(v_inp_uV, i_inp_nA)
        py_vsource.update_capacitor()

    debug_shepherd.vsource_calc_inp_power(0, 0)
    V_cap_pru_V = float(debug_shepherd.vsource_update_capacitor()) * 10**-6
    py_vsource.calc_inp_power(0, 0)
    V_cap_pyt_V = float(py_vsource.update_capacitor()) * 10**-6

    dVCap_pru = V_cap_pru_V - reference_vss["V_storage_V"]
    dVCap_pyt = V_cap_pyt_V - reference_vss["V_storage_V"]
    deviation_pru = round(100*abs(dVCap_pru/dV_cap_V - 1), 3)  # %
    deviation_pyt = round(100*abs(dVCap_pyt/dV_cap_V - 1), 3)  # %
    deviation_rel = round(100*abs(dVCap_pru/dVCap_pyt - 1), 3)  # %
    print(f"CHARGE - VCap goal = {V_cap_V} V, "
          f"py = {V_cap_pyt_V} V (dev={deviation_pyt} %), "
          f"pru = {V_cap_pru_V} V (dev={deviation_pru} %), "
          f"dev_rel = {deviation_rel} %")
    assert deviation_pyt < 10.0  # %
    assert deviation_pru < 10.0  # %
    assert deviation_rel < 1.0  # %
    assert 0


@pytest.mark.hardware
def test_vsource_drain_charge(debug_shepherd: ShepherdDebug, py_vsource: VirtualSource, reference_vss):
    # set desired end-voltage of storage-cap - low enough to disable output
    V_cap_V = 2.300
    dt_s = 1.00

    dV_cap_V = V_cap_V - reference_vss["V_storage_V"]
    I_cOut = - dV_cap_V * reference_vss["C_storage_F"] / dt_s - reference_vss["I_storage_leak_A"]
    P_out_W = I_cOut * reference_vss["V_storage_V"] * reference_vss["eta_out"]
    I_out_A = P_out_W / reference_vss["V_out_V"]
    # prepare fn-parameters
    cal = CalibrationData.from_default()
    I_out_adc_raw = cal.convert_value_to_raw("emulation", "adc_current", I_out_A)
    n_samples = int(dt_s / reference_vss["t_sample_s"])

    print(f"DRAIN - feeding I = {I_out_A} A as {I_out_adc_raw} raw into vSource with {n_samples} steps")
    print(f" PRU VCap = {debug_shepherd.vsource_update_capacitor()} uV")
    print(f" PRU POut = {debug_shepherd.vsource_calc_out_power(I_out_adc_raw)} fW")
    print(f" PRU VOut = {debug_shepherd.vsource_update_boostbuck()} raw")
    print(f" Py  VCap = {py_vsource.update_capacitor()} uV")
    print(f" Py  POut = {py_vsource.calc_out_power(I_out_adc_raw)} fW")
    print(f" Py  VOut = {py_vsource.update_boostbuck()} raw")

    for iter in range(n_samples):
        v_cap, v_raw1 = debug_shepherd.vsource_drain(I_out_adc_raw)  # combines P_in, P_out, V_cap, state_update
        py_vsource.calc_out_power(I_out_adc_raw)
        py_vsource.update_capacitor()
        v_raw2 = py_vsource.update_boostbuck()
        if (v_raw1 < 1) or (v_raw2 < 1):
            print(f"Stopped Drain-loop after {iter}/{n_samples} samples ({round(100*iter/n_samples)} %), because output was disabled")
            break

    debug_shepherd.vsource_calc_out_power(0)
    V_cap_pru_V = float(debug_shepherd.vsource_update_capacitor()) * 10**-6
    V_out_pru_raw = debug_shepherd.vsource_update_boostbuck()
    py_vsource.calc_out_power(0)
    V_cap_pyt_V = float(py_vsource.update_capacitor()) * 10**-6
    V_out_py_raw = py_vsource.update_boostbuck()

    dVCap_ref = reference_vss["V_storage_V"] - reference_vss["V_storage_disable_threshold_V"]
    dVCap_pru = reference_vss["V_storage_V"] - V_cap_pru_V
    dVCap_pyt = reference_vss["V_storage_V"] - V_cap_pyt_V
    deviation_pru = round(100*abs(dVCap_pru / dVCap_ref - 1), 3)  # %
    deviation_pyt = round(100*abs(dVCap_pyt / dVCap_ref - 1), 3)  # %
    deviation_rel = round(100*abs(dVCap_pyt / dVCap_pru - 1), 3)  # %
    print(f"DRAIN - VCap goal = {V_cap_V} V, "
          f"pyt = {V_cap_pyt_V} V (dev={deviation_pyt} %), "
          f"pru = {V_cap_pru_V} V (dev={deviation_pru} %), "
          f"dev_rel = {deviation_rel} %")
    print(f"DRAIN - VOut goal = 0 n, py = {V_out_py_raw} n, pru = {V_out_pru_raw} n")
    assert deviation_pyt < 3.0  # %
    assert deviation_pru < 3.0  # %
    assert deviation_rel < 1.0  # %
    assert V_out_pru_raw < 1  # output disabled
    assert V_out_py_raw < 1
    assert 0

# TODO: add IO-Test with very small values
