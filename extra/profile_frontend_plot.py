import itertools

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

#from profile_frontend_measure import adict

file_list = [
     "profile_emu_00_maiden_v22",
     "profile_emu_01_C6_removed",
     "profile_emu_02_C6_470nF",
     "profile_emu_03_C1C2_2nF",
     "profile_emu_04_R10_LP_22pF",
     "profile_emu_05_R8_ShortLoop",
     "profile_emu_06_ch1_200R_x0uF",
     "profile_emu_06_ch1_200R_x1uF",
     "profile_emu_11_baseline_fullmod",
            ]

file_list_emu = [
     "sheep0_cape_v230c1_profile_00_lab_pwr",
     "sheep0_cape_v230c1_profile_01_10V4V_raise",
     "sheep0_cape_v230c1_profile_02_bridge_L3_inpCoil",
     "sheep0_cape_v230c1_profile_03_full_all",
     "sheep0_cape_v230c1_profile_03_short_all",
     "sheep0_cape_v230c1_profile_04_short_emu_C6_ShuntBuff_to_470nF",
     "sheep0_cape_v230c1_profile_05_full_emu_repaired",
     "sheep0_cape_v230c1_profile_05_short_emu_repaired",
     "sheep0_cape_v230c1_profile_06_short_C6_lowered_100nF",
     "sheep0_cape_v230c1_profile_07_short_C6_increased_1uF",
     "sheep0_cape_v230c1_profile_08_short_DAC_R5_lowpassed",
     "sheep0_cape_v230c1_profile_09_short_C6_removed",
     "sheep0_cape_v230c1_profile_10_short_improved_profiling",
     "sheep0_cape_v230c1_profile_17_shortf_bakeoff",
             ]

file_list_hrv = [
     "sheep0_cape_v230c1_profile_10_short_improved_profiling",  # hrv & emu profile
     "sheep0_cape_v230c1_profile_11_short_hrv_without_sense_base",
     "sheep0_cape_v230c1_profile_12_short_R22_from_100k_to_1k",
     "sheep0_cape_v230c1_profile_13_short_C140_from_22pF_to_1nF",
     "sheep0_cape_v230c1_profile_14_short_C140_to_2nF",
     "sheep0_cape_v230c1_profile_15_short_C35_100nF_removed",
     "sheep0_cape_v230c1_profile_16_short_TP6_with_10nF_ADC_V",
     "sheep0_cape_v230c1_profile_17_shortf_bakeoff",  # hrv & emu profile
     "sheep0_cape_v230c1_profile_18_short_R22_to_100R",
     "sheep0_cape_v230c1_profile_19_short_C140_to_10nF",
     "sheep0_cape_v230c1_profile_20_short_hrv_Shunt_to_10R_gain10",
     "sheep0_cape_v230c1_profile_21_short_hrv_diode_to_SSM",
     "sheep0_cape_v230c1_profile_22_short_C35_to_470nF",
     "sheep0_cape_v230c1_profile_23_short_InputCap_2x100nF",
     "sheep0_cape_v230c1_profile_24_short_C35_removed",
     "sheep0_cape_v230c1_profile_25_short_InputCap_removed",  # next day, zero leak
     "sheep0_cape_v230c1_profile_26_short_R22_33R_10nF",
     "sheep0_cape_v230c1_profile_27_short_C35_add_back_100nF",
     "sheep0_cape_v230c1_profile_28_short_ADC_V_R16_from_1k_to_33R",
     "sheep0_cape_v230c1_profile_29_short_R20_OpAmpFB_from_1k_to_100R",
     "sheep0_cape_v230c1_profile_30_short_R20_OpAmpFB_to_10k",
     "sheep0_cape_v230c1_profile_31_short_R18_from_1k_to_0R",
     "sheep0_cape_v230c1_profile_32_short_R16_back_to_1k",  # SMU restarted, zero leak
     "sheep0_cape_v230c1_profile_33_short_R20_back_to_1k",
     "sheep0_cape_v230c1_profile_34_short_C36_from_1nF_to_10nF",
     "sheep0_cape_v230c1_profile_35_short_R27_from_1k_to_100R",
             ]

file_list = file_list_emu

cgain = 1
coffset = 0
vgain = 1
voffset = 0

adict = {"voltage_shp_V": 0,
         "voltage_shp_raw": 1,
         "voltage_ref_V": 2,
         "current_shp_A": 3,
         "current_shp_raw": 4,
         "current_ref_A": 5,
         }
alist = ["v_shp_V", "v_shp_raw", "v_ref_V", "c_shp_A", "c_shp_raw", "c_ref_A"]


def learn_cal_current(result: pd.DataFrame):
    # chose first voltage above 2.4 V as base, currents range from 60 uA to 14 mA
    result = result.groupby(by=["c_ref_A", "v_shp_V"]).mean().reset_index(drop=False)
    v1 = result[result.v_shp_V >= 2.4].sort_values(by=["v_shp_V"], ignore_index=True).at[0, "v_shp_V"]
    filter0 = (result.c_ref_A >= 60e-6) & (result.c_ref_A <= 14e-3) & (result.v_shp_V == v1)
    result = result[filter0].reset_index(drop=True)
    if filter0.sum() <= 1:
        print("WARNING: skipped a current_calibration")
        return
    global cgain, coffset
    cgain, coffset = measurements_to_calibration(result.c_ref_A, result.c_shp_raw)
    print(f"->resulting C-Cal: gain = {cgain}, offset = {coffset}")


def learn_cal_voltage(result: np.ndarray):
    # chose first current above 60 uA as base, voltages range from 0.3 V to 2.6 V
    result = result.groupby(by=["c_ref_A", "v_shp_V"]).mean().reset_index(drop=False)
    c1 = result[result.c_ref_A >= 60e-6].sort_values(by=["c_ref_A"], ignore_index=True).at[0, "c_ref_A"]
    filter0 = (result.v_shp_V >= 0.3) & (result.v_shp_V <= 2.6) & (result.c_ref_A == c1)
    result = result[filter0].reset_index(drop=True)
    if filter0.sum() <= 1:
        print("WARNING: skipped a voltage_calibration")
        return
    global vgain, voffset
    vgain, voffset = measurements_to_calibration(result.v_ref_V, result.v_shp_raw)
    print(f"->resulting V-Cal: gain = {vgain}, offset = {voffset}")


def cal_convert_current_raw_to_A(input):
    global cgain, coffset
    return input * cgain + coffset


def measurements_to_calibration(ref, raw) -> tuple:
    result = stats.linregress(raw, ref)
    offset = float(result.intercept)
    gain = float(result.slope)
    if result.rvalue < 0.999:
        print(f"WARNING: a calibration had a low rvalue = {result.rvalue}")
    return float(gain), float(offset)


def scatter_setpoints_std(result: np.ndarray, file_name):
    global cgain
    x = 1e3 * result[adict["voltage_ref_V"], :]
    y = list([])
    stddev = list([])
    vol = list([])
    for i in range(result.shape[1]):
        y.append(1e3 * result[adict["current_shp_A"], i])
        value = 1e6 * cgain * np.std(result[adict["current_shp_raw"], i])
        stddev.append(value)
        vol.append(25*value)

    fig, ax = plt.subplots()
    sct = ax.scatter(x, y, c=stddev, s=vol, cmap="turbo", alpha=0.7)

    ax.set_xlabel(r'Voltage [mV]', fontsize=10)
    ax.set_ylabel(r'Current [mA]', fontsize=10)
    ax.set_title(f'Position of Setpoints with Standard-Deviation as color/size (mean = {np.mean(stddev):.2f} uA)')
    plt.colorbar(sct, label="Standard-Deviation [uA]", orientation="vertical", shrink=.7)

    ax.grid(True)
    ax.set_xlim(-500, 5000)
    ax.set_ylim(-5, 50)
    fig.set_figwidth(11)
    fig.set_figheight(10)
    fig.tight_layout()
    plt.savefig(file_name)
    plt.close(fig)
    plt.clf()


def scatter_setpoints_dyn(result: np.ndarray, file_name):
    global cgain
    x = 1e3 * result[adict["voltage_ref_V"], :]
    y = list([])
    dyn = list([])
    vol = list([])
    for i in range(result.shape[1]):
        y.append(1e3 * result[adict["current_shp_A"], i])
        value = 1e6 * cgain * (np.max(result[adict["current_shp_raw"], i]) - np.min(result[adict["current_shp_raw"], i]))
        dyn.append(value)
        vol.append(5*value)

    fig, ax = plt.subplots()
    sct = ax.scatter(x, y, c=dyn, s=vol, cmap="turbo", alpha=0.7)

    ax.set_xlabel(r'Voltage [mV]', fontsize=10)
    ax.set_ylabel(r'Current [mA]', fontsize=10)
    ax.set_title(f'Position of Setpoints with ADC-MinMax-Intervall as color/size (mean = {np.mean(dyn):.2f} uA)')
    plt.colorbar(sct, label="ADC-MinMax-Intervall [uA]", orientation="vertical", shrink=.7)

    ax.grid(True)
    ax.set_xlim(-500, 5000)
    ax.set_ylim(-5, 50)
    fig.set_figwidth(11)
    fig.set_figheight(10)
    fig.tight_layout()
    plt.savefig(file_name)
    plt.close(fig)
    plt.clf()


def quiver_setpoints_offset(data: pd.DataFrame, file_name):
    '''
    global cgain
    x = 1e3 * result[adict["voltage_shp_V"], :]
    y = list([])
    u = list([])
    v = list([])
    w = list([])
    for i in range(result.shape[1]):
        y.append(1e3 * result[adict["current_ref_A"], i])
        value_x = 1 * 1e3 * ((result[adict["voltage_ref_V"], i]) - np.min(result[adict["voltage_shp_V"], i]))
        value_y = 200 * 1e3 * ((result[adict["current_shp_A"], i]) - np.min(result[adict["current_ref_A"], i]))
        u.append(value_x)
        v.append(value_y)
        #w.append((value_x**2 + value_y**2)**0.5)
        w.append(1e6 * ((result[adict["current_shp_A"], i]) - np.min(result[adict["current_ref_A"], i])))
    '''
    fig, ax = plt.subplots()
    ax.scatter(1e3 * data.v_shp_V, 1e3 * data.c_ref_A, c=1e3 * data.c_error_mean_mA, s=10, alpha=0.7, cmap="turbo")
    qpl = ax.quiver(1e3 * data.v_shp_V, 1e3 * data.c_ref_A,  # XY
                    data.v_error_mean_mV, 1e3 * data.c_error_mean_mA,  # UV
                    1e3 * data.c_error_mean_mA,  # W
                    units="xy", scale=1, pivot='tail', cmap="turbo", alpha=0.9)  # pivot: tail, mid, tip
    ax.set_xlabel(r'Voltage [mV]', fontsize=10)
    ax.set_ylabel(r'Current [mA]', fontsize=10)
    ax.set_title(f'Position of Setpoints with Distance from Ref')
    plt.colorbar(qpl, label="Error of Current [uA]", orientation="vertical", shrink=.7)

    ax.grid(True)
    ax.set_xlim(-500, 5500)
    ax.set_ylim(-5, 55)
    fig.set_figwidth(11)
    fig.set_figheight(10)
    fig.tight_layout()
    plt.savefig(file_name)
    plt.close(fig)
    plt.clf()


stat_list = list()
for file in file_list:
    print(f"processing {file}")
    fprofile = np.load(file + ".npz", allow_pickle=True)

    for target in ["a", "b", "h", "emu_a", "emu_b", "hrv"]:

        if target not in fprofile:
            continue
        if (fprofile[target] is None) or (fprofile[target].size < 2):
            continue

        result_np = fprofile[target]

        result_pd = pd.DataFrame(np.transpose(result_np), columns=alist)

        # get the inner 100k-array out - similar to pd.ungroup, but without special cmd
        segment_list = list()
        for idx, row in result_pd.iterrows():
            # c_shp_raw is always np.array, but v_shp_raw only when
            segment_df = pd.DataFrame(row.c_shp_raw, columns=["c_shp_raw"])
            segment_df["c_ref_A"] = row.c_ref_A
            segment_df["c_shp_A"] = row.c_shp_A
            segment_df["v_ref_V"] = row.v_ref_V
            segment_df["v_shp_V"] = row.v_shp_V
            segment_df["v_shp_raw"] = row.v_shp_raw
            segment_list.append(segment_df)
        result_df = pd.concat(segment_list, axis=0)

        #for i in range(result.shape[1]):
            # throw away first measurements
        #    result[adict["current_shp_raw"], i] = result[adict["current_shp_raw"], i][100:]

        # fragment to fix old profiles -> special case when measuring without SourceMeter, but with resistor
        filter_v = result_df.v_ref_V <= -3
        result_df.loc[filter_v, "v_ref_V"] = result_df.loc[filter_v, "v_shp_V"]
        result_df.loc[filter_v, "c_ref_A"] = result_df.loc[filter_v, "c_shp_A"]

        learn_cal_current(result_df)
        learn_cal_voltage(result_df)

        result_df["c_shp_A"] = cal_convert_current_raw_to_A(result_df.c_shp_raw)
        result_df["c_shp_A"] = result_df.c_shp_A.apply(lambda x: x if x >= -1e-3 else -1e-3)
        result_df["v_error_mV"] = 1e3 * (result_df.v_ref_V - result_df.v_shp_V)
        result_df["v_error_abs_mV"] = result_df.v_error_mV.abs()
        result_df["c_error_mA"] = 1e3 * (result_df.c_ref_A - result_df.c_shp_A)
        result_df["c_error_abs_mA"] = result_df.c_error_mA.abs()

        result_condensed = result_df.groupby(by=["c_ref_A", "v_shp_V"]).mean().reset_index(drop=False)
        result_condensed["v_error_mean_mV"] = result_df.groupby(by=["c_ref_A", "v_shp_V"]).v_error_mV.mean().reset_index(drop=True)
        result_condensed["v_error_max_mV"] = result_df.groupby(by=["c_ref_A", "v_shp_V"]).v_error_abs_mV.max().reset_index(drop=True)
        result_condensed["v_error_stddev_mV"] = result_df.groupby(by=["c_ref_A", "v_shp_V"]).v_error_abs_mV.std().reset_index(drop=True)
        result_condensed["c_error_mean_mA"] = result_df.groupby(by=["c_ref_A", "v_shp_V"]).c_error_mA.mean().reset_index(drop=True)
        result_condensed["c_error_max_mA"] = result_df.groupby(by=["c_ref_A", "v_shp_V"]).c_error_abs_mA.max().reset_index(drop=True)
        result_condensed["c_error_stddev_mA"] = result_df.groupby(by=["c_ref_A", "v_shp_V"]).c_error_abs_mA.std().reset_index(drop=True)

        filter_c = (result_df.c_ref_A >= 3e-6) & (result_df.c_ref_A <= 40e-3)
        filter_v = (result_df.v_shp_V >= 1.0) & (result_df.v_shp_V <= 3.9)
        result_filtered = result_df[filter_c & filter_v]

        #scatter_setpoints_std(result_condensed, "profile_scatter_stddev_" + file + "_" + target + ".png")
        #scatter_setpoints_dyn(result_condensed, "profile_scatter_dynamic_" + file + "_" + target + ".png")
        #quiver_setpoints_offset(result_condensed, "profile_quiver_offset_" + file + "_" + target + ".png")

        # stat-generator
        # - every dataset is a row
        # - v_diff_mean @all, @1-4V;0-40mA, over each voltage + each current
        # - v_diff_max @all, @1-4V;0-40mA, over each ...
        # - c_error_mean @all, @1-4V;0-40mA -> abs-value?
        #   min, max, stddev, minmax-intervall, mean

        for decision in [False, True]:
            stat_values = pd.DataFrame()
            result_now = result_filtered if decision else result_df
            stat_values["origin"] = [file + " " + target.upper() + (" limited" if decision else "")]
            stat_values["component"] = target.upper()
            stat_values["range"] = "limited" if decision else "full"

            stat_values["v_error_mean_mV"] = result_now.v_error_abs_mV.mean()
            stat_values["v_error_max_mV"] = result_now.v_error_abs_mV.max()
            stat_values["v_error_std_mV"] = result_now.v_error_abs_mV.std()

            stat_values["c_error_mean_mA"] = result_now.c_error_abs_mA.mean()
            stat_values["c_error_max_mA"] = result_now.c_error_abs_mA.max()
            stat_values["c_error_std_mA"] = result_now.c_error_abs_mA.std()

            stat_list.append(stat_values)

stat_df = pd.concat(stat_list, axis=0)
stat_df.to_csv("profile_analysis.csv", sep=";", decimal=",")
