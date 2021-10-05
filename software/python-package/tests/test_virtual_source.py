import pytest
import subprocess
import time
from pathlib import Path

from shepherd import ShepherdDebug, CalibrationData
from shepherd.virtual_source import VirtualSource


@pytest.fixture
def vs_config(request):
    marker = request.node.get_closest_marker("vs_name")
    if marker is None:
        vs_name = None
    else:
        vs_name = marker.args[0]

    if isinstance(vs_name, str):
        if ".yml" in vs_name:
            if Path(vs_name).exists():
                vsc = Path(vs_name)
            else:
                here = Path(__file__).absolute()
                vsc = here.parent / vs_name
        else:
            vsc = vs_name
    else:
        assert 0
    return vsc


@pytest.fixture
def cal_config():
    return CalibrationData.from_default()


@pytest.fixture()
def pru_vsource(request, shepherd_up, vs_config, cal_config):
    pru = ShepherdDebug()
    request.addfinalizer(pru.__del__)
    pru.__enter__()
    request.addfinalizer(pru.__exit__)
    pru.vsource_init(vs_config, cal_config)
    return pru


@pytest.fixture
def pyt_vsource(vs_config, cal_config):
    return VirtualSource(vs_config, cal_config)


@pytest.fixture
def reference_vss():
    # keep in sync with "example_virtsource_settings.yml"
    vss = {
        "C_intermediate_uF": 100 * (10 ** 0),
        "V_intermediate_mV": 3000,
        "eta_in": 0.5,
        "eta_out": 0.8,
        "I_intermediate_leak_nA": 9 * (10 ** 0),
        "V_intermediate_disable_threshold_mV": 2300,
        "V_output_mV": 2000,
        "t_sample_s": 10 * (10 ** -6)
    }
    return vss


def difference_percent(val1, val2, offset):
    # offset is used for small numbers
    return round(100 * abs((val1 + offset) / (val2 + offset) - 1), 3)


@pytest.mark.hardware
@pytest.mark.vs_name("./example_virtsource_settings.yml")
def test_vsource_add_charge(pru_vsource, pyt_vsource, reference_vss):
    # set desired end-voltage of storage-cap:
    V_cap_mV = 3500
    dt_s = 0.100
    V_inp_mV = 1000
    dV_cap_mV = V_cap_mV - reference_vss["V_intermediate_mV"]
    I_cIn_nA = dV_cap_mV * reference_vss["C_intermediate_uF"] / dt_s
    P_inp_pW = I_cIn_nA * reference_vss["V_intermediate_mV"] / reference_vss["eta_in"]
    I_inp_nA = P_inp_pW / V_inp_mV
    # prepare fn-parameters
    V_inp_uV = int(V_inp_mV * 10**3)
    I_inp_nA = int(I_inp_nA * 10**0)
    n_samples = int(dt_s / reference_vss["t_sample_s"])
    print(f"CHARGE - feeding I = {I_inp_nA} nA, V = {V_inp_mV} mV into vSource with {n_samples} steps")
    print(f" PRU VCap = {pru_vsource.vsource_update_cap_storage()} uV")
    print(f" PRU PInp = {pru_vsource.vsource_calc_inp_power(V_inp_uV, I_inp_nA)} fW")
    print(f" Py  VCap = {pyt_vsource.update_cap_storage()} uV")
    print(f" Py  PInp = {pyt_vsource.calc_inp_power(V_inp_uV, I_inp_nA)} fW")

    for _ in range(n_samples):
        pru_vsource.vsource_charge(V_inp_uV, I_inp_nA)  # combines P_in, P_out, V_cap, state_update
        pyt_vsource.calc_inp_power(V_inp_uV, I_inp_nA)
        pyt_vsource.update_cap_storage()

    pru_vsource.vsource_calc_inp_power(0, 0)
    V_cap_pru_mV = float(pru_vsource.vsource_update_cap_storage()) * 10**-3
    pyt_vsource.calc_inp_power(0, 0)
    V_cap_pyt_mV = float(pyt_vsource.update_cap_storage()) * 10 ** -3

    dVCap_pru = V_cap_pru_mV - reference_vss["V_intermediate_mV"]
    dVCap_pyt = V_cap_pyt_mV - reference_vss["V_intermediate_mV"]
    deviation_pru = difference_percent(dVCap_pru, dV_cap_mV, 40)  # %
    deviation_pyt = difference_percent(dVCap_pyt, dV_cap_mV, 40)  # %
    deviation_rel = difference_percent(dVCap_pru, dVCap_pyt, 40)  # %
    print(f"CHARGE - VCap goal = {V_cap_mV} mV, "
          f"py = {V_cap_pyt_mV} mV (dev={deviation_pyt} %), "
          f"pru = {V_cap_pru_mV} mV (dev={deviation_pru} %), "
          f"dev_rel = {deviation_rel} %")
    assert deviation_pyt < 10.0  # %
    assert deviation_pru < 10.0  # %
    assert deviation_rel < 1.0  # %


@pytest.mark.hardware
@pytest.mark.vs_name("./example_virtsource_settings.yml")
def test_vsource_drain_charge(pru_vsource, pyt_vsource, reference_vss):
    # set desired end-voltage of storage-cap - low enough to disable output
    V_cap_mV = 2300
    dt_s = 0.50

    dV_cap_mV = V_cap_mV - reference_vss["V_intermediate_mV"]
    I_cOut_nA = - dV_cap_mV * reference_vss["C_intermediate_uF"] / dt_s - reference_vss["I_intermediate_leak_nA"]
    P_out_pW = I_cOut_nA * reference_vss["V_intermediate_mV"] * reference_vss["eta_out"]
    I_out_nA = P_out_pW / reference_vss["V_output_mV"]
    # prepare fn-parameters
    cal = CalibrationData.from_default()
    I_out_adc_raw = cal.convert_value_to_raw("emulation", "adc_current", I_out_nA * 10**-9)
    n_samples = int(dt_s / reference_vss["t_sample_s"])

    print(f"DRAIN - feeding I = {I_out_nA} nA as {I_out_adc_raw} raw into vSource with {n_samples} steps")
    print(f" PRU VCap = {pru_vsource.vsource_update_cap_storage()} uV")
    print(f" PRU POut = {pru_vsource.vsource_calc_out_power(I_out_adc_raw)} fW")
    print(f" PRU VOut = {pru_vsource.vsource_update_states_and_output()} raw")
    print(f" Py  VCap = {pyt_vsource.update_cap_storage()} uV")
    print(f" Py  POut = {pyt_vsource.calc_out_power(I_out_adc_raw)} fW")
    print(f" Py  VOut = {pyt_vsource.update_states_and_output()} raw")

    for index in range(n_samples):
        v_cap, v_raw1 = pru_vsource.vsource_drain(I_out_adc_raw)  # combines P_in, P_out, V_cap, state_update
        pyt_vsource.calc_out_power(I_out_adc_raw)
        pyt_vsource.update_cap_storage()
        v_raw2 = pyt_vsource.update_states_and_output()
        if (v_raw1 < 1) or (v_raw2 < 1):
            print(f"Stopped Drain-loop after {index}/{n_samples} samples ({round(100*index/n_samples)} %), because output was disabled")
            break

    pru_vsource.vsource_calc_out_power(0)
    V_mid_pru_mV = float(pru_vsource.vsource_update_cap_storage()) * 10**-3
    V_out_pru_raw = pru_vsource.vsource_update_states_and_output()
    pyt_vsource.calc_out_power(0)
    V_mid_pyt_mV = float(pyt_vsource.update_cap_storage()) * 10 ** -3
    V_out_pyt_raw = pyt_vsource.update_states_and_output()

    dVCap_ref = reference_vss["V_intermediate_mV"] - reference_vss["V_intermediate_disable_threshold_mV"]
    dVCap_pru = reference_vss["V_intermediate_mV"] - V_mid_pru_mV
    dVCap_pyt = reference_vss["V_intermediate_mV"] - V_mid_pyt_mV
    deviation_pru = difference_percent(dVCap_pru, dVCap_ref, 40)  # %
    deviation_pyt = difference_percent(dVCap_pyt, dVCap_ref, 40)  # %
    deviation_rel = difference_percent(dVCap_pyt, dVCap_pru, 40)  # %
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


@pytest.mark.hardware
@pytest.mark.vs_name("direct")  # easiest case: v_inp == v_out, current not
def test_vsource_direct(pru_vsource, pyt_vsource):
    for voltage_mV in [0, 100, 500, 1000, 2000, 3000, 4000, 4500]:
        V_pru_mV = pru_vsource.iterate(voltage_mV * 10**3, 0, 0) * 10**-3
        V_pyt_mV = pyt_vsource.iterate(voltage_mV * 10**3, 0, 0) * 10**-3
        print(f"DirectSRC - Inp = {voltage_mV} mV, OutPru = {V_pru_mV} mV, OutPy = {V_pyt_mV} mV")
        assert difference_percent(V_pru_mV, voltage_mV, 50) < 3
        assert difference_percent(V_pyt_mV, voltage_mV, 50) < 3


@pytest.mark.hardware
@pytest.mark.vs_name("diode+capacitor")
def test_vsource_diodecap(pru_vsource, pyt_vsource):
    voltages_mV = [1000, 1100, 1500, 2000, 2500, 3000, 3500, 4000, 4500]

    # input with lower voltage should not change (open) output
    V_pru_mV = pru_vsource.iterate(0, 0, 0) * 10**-3
    V_pyt_mV = pyt_vsource.iterate(0, 0, 0) * 10**-3
    A_in_nA = 10**3
    for V_in_mV in voltages_mV[0:4]:  # NOTE: make sure this selection is below cap-init-voltage
        V_pru2_mV = pru_vsource.iterate(V_in_mV * 10**3, A_in_nA, 0) * 10**-3
        V_pyt2_mV = pyt_vsource.iterate(V_in_mV * 10**3, A_in_nA, 0) * 10**-3
        assert V_pru_mV == V_pru2_mV
        assert V_pyt_mV == V_pyt2_mV
        print(f"DiodeCap LowInput - Inp = {V_in_mV} mV, OutPru = {V_pru2_mV} mV, OutPy = {V_pyt2_mV} mV")
    assert pyt_vsource.P_in_fW >= pyt_vsource.P_out_fW
    assert pru_vsource.P_in_fW >= pru_vsource.P_out_fW

    # drain Cap for next tests
    V_target_mV = 500
    A_out_nA = 10**7
    steps_needed = [0, 0]
    while pru_vsource.iterate(0, 0, A_out_nA) > V_target_mV * 10**3:
        steps_needed[0] += 1
    while pyt_vsource.iterate(0, 0, A_out_nA) > V_target_mV * 10**3:
        steps_needed[1] += 1
    print(f"DiodeCap Draining to {V_target_mV} mV needed {steps_needed} (pru, py) steps")
    pru_vsource.P_in_fW = 0
    pru_vsource.P_out_fW = 0
    pyt_vsource.P_in_fW = 0
    pyt_vsource.P_out_fW = 0

    # zero current -> no change in output
    A_in_nA = 0
    for V_in_mV in voltages_mV:
        V_pru_mV = pru_vsource.iterate(V_in_mV * 10**3, A_in_nA, 0) * 10**-3
        V_pyt_mV = pyt_vsource.iterate(V_in_mV * 10**3, A_in_nA, 0) * 10**-3
        print(f"DiodeCap inp=0nA - Inp = {V_in_mV} mV, OutPru = {V_pru_mV} mV, OutPy = {V_pyt_mV} mV")
        assert difference_percent(V_pru_mV, V_target_mV, 50) < 3
        assert difference_percent(V_pyt_mV, V_target_mV, 50) < 3

    # feed 200 mA -> fast charging cap
    A_in_nA = 2 * 10 ** 8
    for V_in_mV in voltages_mV:
        for _ in range(100):
            V_pru_mV = pru_vsource.iterate(V_in_mV * 10**3, A_in_nA, 0) * 10**-3
            V_pyt_mV = pyt_vsource.iterate(V_in_mV * 10**3, A_in_nA, 0) * 10**-3
        V_postDiode_mV = max(V_in_mV - 300, 0)  # diode drop voltage
        print(f"DiodeCap inp=200mA - Inp = {V_in_mV} mV, PostDiode = {V_postDiode_mV} mV, OutPru = {V_pru_mV} mV, OutPy = {V_pyt_mV} mV")
        assert difference_percent(V_pru_mV, V_postDiode_mV, 50) < 3
        assert difference_percent(V_pyt_mV, V_postDiode_mV, 50) < 3

    # feed 5 mA, drain double of that -> output should settle at (V_in - V_drop)/2
    # TODO: wrong for this mode
    V_in_uV = 3 * 10**6
    A_in_nA = 5 * 10**6
    A_out_nA = 2 * A_in_nA
    for _ in range(100):
        V_pru_mV = pru_vsource.iterate(V_in_uV, A_in_nA, A_out_nA) * 10**-3
        V_pyt_mV = pyt_vsource.iterate(V_in_uV, A_in_nA, A_out_nA) * 10**-3

    V_settle_mV = (V_in_uV * 10**-3 - 300) / 2
    print(f"DiodeCap Drain in=5mA,out=10mA - Inp = {V_in_uV/10**3} mV, Settle = {V_settle_mV} mV, OutPru = {V_pru_mV} mV, OutPy = {V_pyt_mV} mV")
    # assert difference_percent(V_pru_mV, V_settle_mV, 50) < 3
    # assert difference_percent(V_pyt_mV, V_settle_mV, 50) < 3
    assert pyt_vsource.P_in_fW >= pyt_vsource.P_out_fW
    assert pru_vsource.P_in_fW >= pru_vsource.P_out_fW

# TODO: add IO-Test with very small and very large values
# unit-test low and high power inputs 72W, 1W, 195 nA * 19 uV = 3.7 pW, what is with 1fW?
# unit test different regulators
