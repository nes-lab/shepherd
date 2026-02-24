"""
shepherd.target_io for Cape HW v25e
~~~~~
Lib to talk to the targets. there are 12x GPIO including 1x UART.
There are also four programming pins (SWD, SBW or JTAG)
IO has semi-static direction, low-drain, and is capable for several MBit

GPIO 0        - dir-group A / rxtx, UART Target Rx
GPIO 1        - always RX, UART Target Tx
GPIO 2        - dir-group B / rxtx
GPIO 3        - dir-group B / rxtx
GPIO 4        - dir-group C / rxtx
GPIO 5        - dir-group C / rxtx
GPIO 6        - dir-group C / rxtx
GPIO 7        - dir-group C / rxtx
GPIO 8        - always rx
GPIO 9        - always rx, not mapped to sys
GPIO 10       - always rx, not mapped to sys
GPIO 11       - always rx, not mapped to sys
PWR GOOD LOW  - always TX, not mapped to sys
PWR GOOD HIGH - always TX, not mapped to sys

Prog1 CLK - jtag TCK   - always TX
Prog1 IO  - jtag TDI   - pgmDir1 / rxtx
Prog2 CLK - jtag TDO   - always TX
Prog2 IO  - jtag TMS   - pgmDir2 / rxtx

Direction Pins:

dir-group A = 78  # P8_37, GPIO2[14], controls 1 GPIO
dir-group B = 79  # P8_38, GPIO2[15], controls 2 GPIO
dir-group C = 50  # P9_14, GPIO1[18], controls 4 GPIO
prgDir1 = 10   # P8_31, GPIO0[10]
prgDir2 = 11   # P8_32, GPIO0[11]

"""

from collections.abc import Mapping

target_pins: list[dict] = [  # pin-order from target-connector
    {"name": "gpio0", "pin": 14, "dir": 78},  # group A
    {"name": "gpio1", "pin": 15, "dir": "I"},
    {"name": "gpio2", "pin": 46, "dir": 79},  # group B
    {"name": "gpio3", "pin": 47, "dir": 79},  # group B
    {"name": "gpio4", "pin": 61, "dir": 50},  # group C
    {"name": "gpio5", "pin": 80, "dir": 50},  # group C
    {"name": "gpio6", "pin": 81, "dir": 50},  # group C
    {"name": "gpio7", "pin": 26, "dir": 50},  # group C
    {"name": "gpio8", "pin": 27, "dir": "I"},
    # {"name": "gpio9"},  # these have no sys-pin connected
    # {"name": "gpio10"},
    # {"name": "gpio11"},
    # {"name": "pwr_good_low"},
    # {"name": "pwr_good_high"},
    {"name": "prog1_clk", "pin": 5, "dir": "O"},  # P9_17
    {"name": "prog1_io", "pin": 4, "dir": 10},  # P9_18, dir P8_31
    {"name": "prog2_clk", "pin": 8, "dir": "O"},  # P8_35
    {"name": "prog2_io", "pin": 9, "dir": 11},  # P8_33, dir P8_32, noqa: CM001
]

target_port_to_cape_mapping: Mapping[int, int] = {
    0: 0,  # UART Target RX
    1: 1,  # UART Target TX
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    11: 11,
    16: 12,  # powerGood Low
    17: 13,  # powerGood High
}

# fmt: off
# ruff: noqa: E501
GPIO_LOG_BIT_POSITIONS: Mapping[int, Mapping[str, str]] = {
    0: {"pru_reg":  "r31_00", "name": "tgt_gpio00_uRx", "bb_pin": "P8_45", "sys_pin": "P9_26", "sys_reg": "14"},
    1: {"pru_reg":  "r31_01", "name": "tgt_gpio01_uTx", "bb_pin": "P8_46", "sys_pin": "P9_24", "sys_reg": "15"},
    2: {"pru_reg":  "r31_02", "name": "tgt_gpio02",     "bb_pin": "P8_43", "sys_pin": "P8_16", "sys_reg": "46"},
    3: {"pru_reg":  "r31_03", "name": "tgt_gpio03",     "bb_pin": "P8_44", "sys_pin": "P8_15", "sys_reg": "47"},
    4: {"pru_reg":  "r31_04", "name": "tgt_gpio04",     "bb_pin": "P8_41", "sys_pin": "P8_26", "sys_reg": "61"},
    5: {"pru_reg":  "r31_05", "name": "tgt_gpio05",     "bb_pin": "P8_42", "sys_pin": "P8_36", "sys_reg": "80"},
    6: {"pru_reg":  "r31_06", "name": "tgt_gpio06",     "bb_pin": "P8_39", "sys_pin": "P8_34", "sys_reg": "81"},
    7: {"pru_reg":  "r31_07", "name": "tgt_gpio07",     "bb_pin": "P8_40", "sys_pin": "P8_14", "sys_reg": "26"},
    8: {"pru_reg":  "r31_08", "name": "tgt_gpio08",     "bb_pin": "P8_27", "sys_pin": "P8_17", "sys_reg": "27"},
    9: {"pru_reg":  "r31_09", "name": "tgt_gpio09",     "bb_pin": "P8_29", "sys_pin": "",      "sys_reg": ""},
    10: {"pru_reg": "r31_10", "name": "tgt_gpio10",     "bb_pin": "P8_28", "sys_pin": "",      "sys_reg": ""},
    11: {"pru_reg": "r31_11", "name": "tgt_gpio11",     "bb_pin": "P8_30", "sys_pin": "",      "sys_reg": ""},
    12: {"pru_reg": "r30_05", "name": "pwr_good_low",   "bb_pin": "P9_27", "sys_pin": "",      "sys_reg": ""},
    13: {"pru_reg": "r30_06", "name": "pwr_good_high",  "bb_pin": "P9_41B","sys_pin": "",      "sys_reg": ""},
}
# Note: this table is copied (for hdf5-reference) from pru1/include/hw_config.h
# Note: shepherd-core has gpio-models + data! this lives now in
#       shepherd_core/shepherd_core/data_models/testbed/gpio_fixture.yaml
# fmt: on
