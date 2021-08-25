import itertools

import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression

#from profile_frontend_measure import adict

file_list = ["profile_emu_channels"]
cgain = 1
coffset = 0
vgain = 1
voffset = 0

adict = {"voltage_shp_V": 0,
         "voltage_shp_raw": 1,
         "voltage_ref_V": 2,
         "current_shp_A": 3,
         "current_shp_raw": 4,
         "current_ref_A" : 5,
         }


def cal_current_learn(result: np.ndarray):
    cref = adict["current_ref_A"]
    craw = adict["current_shp_raw"]
    vshp = adict["voltage_shp_V"]
    filter0 = (result[cref, :] == 0) & (result[vshp, :] == 2.5)
    filter1 = (result[cref, :] == 10e-3) & (result[vshp, :] == 2.5)
    global cgain, coffset
    cgain, coffset = measurements_to_calibration([result[cref, filter0].mean(), result[cref, filter1].mean()],
                                                 [result[craw, filter0][0].mean(), result[craw, filter1][0].mean()])


def cal_voltage_learn(result: np.ndarray):
    cref = adict["current_ref_A"]
    vshp = adict["voltage_shp_V"]
    vraw = adict["voltage_shp_raw"]
    vref = adict["voltage_ref_V"]
    filter0 = (result[cref, :] == 1e-3) & (result[vshp, :] == 0.5)
    filter1 = (result[cref, :] == 1e-3) & (result[vshp, :] == 2.5)
    global vgain, voffset
    vgain, voffset = measurements_to_calibration([result[vref, filter0].mean(), result[vref, filter1].mean()],
                                                 [result[vraw, filter0].mean(), result[vraw, filter1].mean()])


def cal_convert_current_raw_to_V(input):
    global cgain, coffset
    return input * cgain + coffset


def measurements_to_calibration(ref, raw) -> tuple:
    x = np.empty(len(ref))
    y = np.empty(len(raw))
    for i in range(len(ref)):
        x[i] = raw[i]
        y[i] = ref[i]
    WLS = LinearRegression()
    WLS.fit(x.reshape(-1, 1), y.reshape(-1, 1), sample_weight=1.0 / x)
    intercept = WLS.intercept_
    slope = WLS.coef_[0]
    return float(slope), float(intercept)  # gain, offset


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
    plt.clf()


def quiver_setpoints_offset(result: np.ndarray, file_name):
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

    fig, ax = plt.subplots()
    ax.scatter(x, y, c=w, s=10, alpha=0.7, cmap="turbo")
    qpl = ax.quiver(x, y, u, v, w, units="xy", scale=1/3, pivot='tail', cmap="turbo", alpha=0.9) # pivot: tail, mid, tip
    ax.set_xlabel(r'Voltage [mV]', fontsize=10)
    ax.set_ylabel(r'Current [mA]', fontsize=10)
    ax.set_title(f'Position of Setpoints with Distance from Ref')
    plt.colorbar(qpl, label="Error of Current [uA]", orientation="vertical", shrink=.7)

    ax.grid(True)
    ax.set_xlim(-500, 5000)
    ax.set_ylim(-5, 50)
    fig.set_figwidth(11)
    fig.set_figheight(10)
    fig.tight_layout()
    plt.savefig(file_name)
    plt.clf()


for file in file_list:
    fprofile = np.load(file + ".npz", allow_pickle=True)

    for target in ["a", "b"]:
        result = fprofile[target]
        cal_current_learn(result)
        cal_voltage_learn(result)

        for i in range(result.shape[1]):
            result[adict["current_shp_A"], i] = cal_convert_current_raw_to_V(np.mean(result[adict["current_shp_raw"], i]))

        filter = (result[adict["current_ref_A"], :] >= 5e-3) | (result[adict["current_ref_A"], :] == 0.0)
        filter &= (result[adict["voltage_shp_V"], :] >= 500e-3) | (result[adict["voltage_shp_V"], :] == 0.0)
        #result = result[:, filter]

        scatter_setpoints_std(result, file + "_scatter_stddev_" + target + ".png")
        scatter_setpoints_dyn(result, file + "_scatter_dynamic_" + target + ".png")
        quiver_setpoints_offset(result, file + "_quiver_offset_" + target + ".png")

print(1)
