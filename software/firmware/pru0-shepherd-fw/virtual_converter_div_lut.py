# noqa: INP001
from pathlib import Path

from matplotlib import pyplot as plt


def div_uV_n4_v1(power_fW_n4: float, voltage_uV: float) -> int:
    DIV_SHIFT = 17  # ~ 131 mV
    LUT_div_uV_n27 = [
        16383,
        683,
        410,
        293,
        228,
        186,
        158,
        137,
        120,
        108,
        98,
        89,
        82,
        76,
        71,
        66,
        62,
        59,
        55,
        53,
        50,
        48,
        46,
        44,
        42,
        40,
        39,
        37,
        36,
        35,
        34,
        33,
        32,
        31,
        30,
        29,
        28,
        27,
        27,
        26,
    ]
    DIV_LUT_SIZE = len(LUT_div_uV_n27)
    lut_pos = int(voltage_uV) // 2**DIV_SHIFT
    lut_pos = min(lut_pos, DIV_LUT_SIZE - 1)
    return (int(power_fW_n4 / 2**10) * LUT_div_uV_n27[lut_pos]) // 2**17


def div_uV_n4_v2(power_fW_n4: float, voltage_uV: float) -> int:
    """ "
    current_nA = power_fW / voltage_uV              -> baseline
    current_nA_n4 = power_fW_n4 * 1 / voltage_uV    -> wanted format
    current_nA_n4 = (power_fW_n4 / 1_n15) * (1_n15 / voltage_uV)
    current_nA_n4 = power_fW_n4 * (1_n15 / voltage_uV_p17) / 1_n17 / 1_n15
    current_nA_n4 = power_fW_n4 * (1_n15 / voltage_uV_p17) / 1_n32
    """
    DIV_pW_SHIFT = 2**15
    DIV_uV_SHIFT = 2**17
    LUT_div = [round(DIV_pW_SHIFT / (n + 0.5)) for n in range(128)]
    DIV_LUT_SIZE = len(LUT_div)
    lut_pos = int(voltage_uV) // DIV_uV_SHIFT
    lut_pos = min(lut_pos, DIV_LUT_SIZE - 1)
    return (int(power_fW_n4) * LUT_div[lut_pos]) // DIV_uV_SHIFT // DIV_pW_SHIFT


fig, ax = plt.subplots(figsize=(18, 8), layout="tight")

power_fW = 5_000_000_000_000
voltages_uV = list(range(1_500_000, 10_000_000, 10_000))

currents_nA = [power_fW / V_uV for V_uV in voltages_uV]
ax.plot(voltages_uV, currents_nA, label="ground_truth")

currents_nA = [div_uV_n4_v1(power_fW * 2**4, V_uV) // 2**4 for V_uV in voltages_uV]
ax.plot(voltages_uV, currents_nA, label="div_uv_n4_v1 (before battery)")

currents_nA = [div_uV_n4_v2(power_fW * 2**4, V_uV) // 2**4 for V_uV in voltages_uV]
ax.plot(voltages_uV, currents_nA, label="div_uv_n4_v2")

ax.legend()
fig.savefig(Path(__file__).with_suffix(".png"))
plt.close()

LUT_div = [round(2**15 / (n + 0.5)) for n in range(128)]
print(", ".join([str(min(div, 2**16-1)) for div in LUT_div]))  # noqa: T201
