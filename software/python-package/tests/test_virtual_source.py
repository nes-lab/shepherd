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
def pyt_vsource():
    cal = CalibrationData.from_default()
    here = Path(__file__).absolute()
    vss = here.parent / "./example_virtsource_settings.yml"
    return VirtualSource(vss, cal)


@pytest.fixture
def reference_vss():
    vss = dict()
    # keep in sync with "example_virtsource_settings.yml"
    vss["C_intermediate_uF"] = 100 * (10**0)
    vss["V_intermediate_mV"] = 3000
    vss["eta_in"] = 0.5
    vss["eta_out"] = 0.8
    vss["I_intermediate_leak_nA"] = 9 * (10**0)
    vss["V_intermediate_disable_threshold_mV"] = 2300
    vss["V_output_mV"] = 2000
    vss["t_sample_s"] = 10 * (10**-6)
    return vss


@pytest.mark.hardware
def test_vsource_add_charge(debug_shepherd: ShepherdDebug, pyt_vsource, reference_vss):
    # set desired end-voltage of storage-cap:
    V_cap_mV = 3500
    dt_s = 0.100
    V_inp_mV = 1000
    dV_cap_mV = V_cap_mV - reference_vss["V_intermediate_mV"]
    I_cIn_nA = dV_cap_mV * reference_vss["C_intermediate_uF"] / dt_s
    P_inp_pW = I_cIn_nA * reference_vss["V_intermediate_mV"] / reference_vss["eta_in"]
    I_inp_nA = P_inp_pW / V_inp_mV
    # prepare fn-parameters
    v_inp_uV = int(V_inp_mV * 10**3)
    i_inp_nA = int(I_inp_nA * 10**0)
    n_samples = int(dt_s / reference_vss["t_sample_s"])
    print(f"CHARGE - feeding I = {I_inp_nA} nA, V = {V_inp_mV} mV into vSource with {n_samples} steps")
    print(f" PRU VCap = {debug_shepherd.vsource_update_cap_storage()} uV")
    print(f" PRU PInp = {debug_shepherd.vsource_calc_inp_power(v_inp_uV, i_inp_nA)} fW")
    print(f" Py  VCap = {pyt_vsource.update_cap_storage()} uV")
    print(f" Py  PInp = {pyt_vsource.calc_inp_power(v_inp_uV, i_inp_nA)} fW")

    for iter in range(n_samples):
        debug_shepherd.vsource_charge(v_inp_uV, i_inp_nA)  # combines P_in, P_out, V_cap, state_update
        pyt_vsource.calc_inp_power(v_inp_uV, i_inp_nA)
        pyt_vsource.update_cap_storage()

    debug_shepherd.vsource_calc_inp_power(0, 0)
    V_cap_pru_mV = float(debug_shepherd.vsource_update_cap_storage()) * 10 ** -3
    pyt_vsource.calc_inp_power(0, 0)
    V_cap_pyt_mV = float(pyt_vsource.update_cap_storage()) * 10 ** -3

    dVCap_pru = V_cap_pru_mV - reference_vss["V_intermediate_mV"]
    dVCap_pyt = V_cap_pyt_mV - reference_vss["V_intermediate_mV"]
    deviation_pru = round(100*abs(dVCap_pru/dV_cap_mV - 1), 3)  # %
    deviation_pyt = round(100*abs(dVCap_pyt/dV_cap_mV - 1), 3)  # %
    deviation_rel = round(100*abs(dVCap_pru/dVCap_pyt - 1), 3)  # %
    print(f"CHARGE - VCap goal = {V_cap_mV} mV, "
          f"py = {V_cap_pyt_mV} mV (dev={deviation_pyt} %), "
          f"pru = {V_cap_pru_mV} mV (dev={deviation_pru} %), "
          f"dev_rel = {deviation_rel} %")
    assert deviation_pyt < 10.0  # %
    assert deviation_pru < 10.0  # %
    assert deviation_rel < 1.0  # %


@pytest.mark.hardware
def test_vsource_drain_charge(debug_shepherd: ShepherdDebug, pyt_vsource, reference_vss):
    # set desired end-voltage of storage-cap - low enough to disable output
    V_cap_mV = 2300
    dt_s = 1.00

    dV_cap_mV = V_cap_mV - reference_vss["V_intermediate_mV"]
    I_cOut_nA = - dV_cap_mV * reference_vss["C_intermediate_uF"] / dt_s - reference_vss["I_intermediate_leak_nA"]
    P_out_pW = I_cOut_nA * reference_vss["V_intermediate_mV"] * reference_vss["eta_out"]
    I_out_nA = P_out_pW / reference_vss["V_output_mV"]
    # prepare fn-parameters
    cal = CalibrationData.from_default()
    I_out_adc_raw = cal.convert_value_to_raw("emulation", "adc_current", I_out_nA * 10**-9)
    n_samples = int(dt_s / reference_vss["t_sample_s"])

    print(f"DRAIN - feeding I = {I_out_nA} nA as {I_out_adc_raw} raw into vSource with {n_samples} steps")
    print(f" PRU VCap = {debug_shepherd.vsource_update_cap_storage()} uV")
    print(f" PRU POut = {debug_shepherd.vsource_calc_out_power(I_out_adc_raw)} fW")
    print(f" PRU VOut = {debug_shepherd.vsource_update_states_and_output()} raw")
    print(f" Py  VCap = {pyt_vsource.update_cap_storage()} uV")
    print(f" Py  POut = {pyt_vsource.calc_out_power(I_out_adc_raw)} fW")
    print(f" Py  VOut = {pyt_vsource.update_states_and_output()} raw")

    for iter in range(n_samples):
        v_cap, v_raw1 = debug_shepherd.vsource_drain(I_out_adc_raw)  # combines P_in, P_out, V_cap, state_update
        pyt_vsource.calc_out_power(I_out_adc_raw)
        pyt_vsource.update_cap_storage()
        v_raw2 = pyt_vsource.update_states_and_output()
        if (v_raw1 < 1) or (v_raw2 < 1):
            print(f"Stopped Drain-loop after {iter}/{n_samples} samples ({round(100*iter/n_samples)} %), because output was disabled")
            break

    debug_shepherd.vsource_calc_out_power(0)
    V_mid_pru_mV = float(debug_shepherd.vsource_update_cap_storage()) * 10**-3
    V_out_pru_raw = debug_shepherd.vsource_update_states_and_output()
    pyt_vsource.calc_out_power(0)
    V_mid_pyt_mV = float(pyt_vsource.update_cap_storage()) * 10 ** -3
    V_out_pyt_raw = pyt_vsource.update_states_and_output()

    dVCap_ref = reference_vss["V_intermediate_mV"] - reference_vss["V_intermediate_disable_threshold_mV"]
    dVCap_pru = reference_vss["V_intermediate_mV"] - V_mid_pru_mV
    dVCap_pyt = reference_vss["V_intermediate_mV"] - V_mid_pyt_mV
    deviation_pru = round(100*abs(dVCap_pru / dVCap_ref - 1), 3)  # %
    deviation_pyt = round(100*abs(dVCap_pyt / dVCap_ref - 1), 3)  # %
    deviation_rel = round(100*abs(dVCap_pyt / dVCap_pru - 1), 3)  # %
    print(f"DRAIN - VCap goal = {V_cap_mV} mV, "
          f"pyt = {V_mid_pyt_mV} mV (dev={deviation_pyt} %), "
          f"pru = {V_mid_pru_mV} mV (dev={deviation_pru} %), "
          f"dev_rel = {deviation_rel} %")
    print(f"DRAIN - VOut goal = 0 n, py = {V_out_pyt_raw} n, pru = {V_out_pru_raw} n")
    assert deviation_pyt < 3.0  # %
    assert deviation_pru < 3.0  # %
    assert deviation_rel < 1.0  # %
    assert V_out_pru_raw < 1  # output disabled
    assert V_out_pyt_raw < 1


# TODO: add IO-Test with very small and very large values
