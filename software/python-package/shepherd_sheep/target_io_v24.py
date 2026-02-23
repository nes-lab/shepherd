"""
shepherd.target_io for Cape HW v24
~~~~~
Lib to talk to the targets. there are 7x GPIO, 1x UART and 2x SWD (or 1x JTAG)
IO has semi-static direction, low-power, and is good for several MBit

GPIO 0            - dir1-pin / rxtx
GPIO 1            - dir1-pin / rxtx
GPIO 2            - dir1-pin / rxtx
GPIO 3            - dir1-pin / rxtx
GPIO 4            - always RX
GPIO 5            - always RX
GPIO 6            - always RX
GPIO 7 - uart rx  - always RX
GPIO 8 - uart tx  - dir2-pin / rxtx
BAT OK            - always TX

Prog1 CLK - jtag TCK   - always TX
Prog1 IO  - jtag TDI   - pDir1-pin / rxtx
Prog2 CLK - jtag TDO   - always TX
Prog2 IO  - jtag TMS   - pDir2-pin / rxtx

Direction Pins:

gpio0to3 = 78  # P8_37, GPIO2[14]
uart_tx = 79   # P8_38, GPIO2[15]
prog1_io = 10   # P8_31, GPIO0[10]
prog2_io = 11   # P8_32, GPIO0[11]

"""

from collections.abc import Mapping

target_pins: list[dict] = [  # pin-order from target-connector
    {"name": "gpio0", "pin": 26, "dir": 78},
    {"name": "gpio1", "pin": 27, "dir": 78},
    {"name": "gpio2", "pin": 46, "dir": 78},
    {"name": "gpio3", "pin": 47, "dir": 78},
    {"name": "gpio4", "pin": 61, "dir": "I"},
    {"name": "gpio5", "pin": 80, "dir": "I"},
    {"name": "gpio6", "pin": 81, "dir": "I"},
    {"name": "uart_rx", "pin": 14, "dir": "I"},
    {"name": "uart_tx", "pin": 15, "dir": 79},  # TODO: why not BatOK here?
    {"name": "prog1_clk", "pin": 5, "dir": "O"},  # P9_17
    {"name": "prog1_io", "pin": 4, "dir": 10},  # P9_18, dir P8_31
    {"name": "prog2_clk", "pin": 8, "dir": "O"},  # P8_35
    {"name": "prog2_io", "pin": 9, "dir": 11},  # P8_33, dir P8_32, noqa: CM001
]

target_port_to_cape_mapping: Mapping[int, int] = {
    0: 8,  # UART Target RX
    1: 7,  # UART Target TX
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 0,
    8: 1,
    17: 9,  # BatOK aka PowerGoodH
}

# fmt: off
# ruff: noqa: E501
GPIO_LOG_BIT_POSITIONS: Mapping[int, Mapping[str, str]]  = {
    0: {"pru_reg": "r31_00", "name": "tgt_gpio0",   "bb_pin": "P8_45", "sys_pin": "P8_14", "sys_reg": "26"},
    1: {"pru_reg": "r31_01", "name": "tgt_gpio1",   "bb_pin": "P8_46", "sys_pin": "P8_17", "sys_reg": "27"},
    2: {"pru_reg": "r31_02", "name": "tgt_gpio2",   "bb_pin": "P8_43", "sys_pin": "P8_16", "sys_reg": "14"},
    3: {"pru_reg": "r31_03", "name": "tgt_gpio3",   "bb_pin": "P8_44", "sys_pin": "P8_15", "sys_reg": "15"},
    4: {"pru_reg": "r31_04", "name": "tgt_gpio4",   "bb_pin": "P8_41", "sys_pin": "P8_26", "sys_reg": "29"},
    5: {"pru_reg": "r31_05", "name": "tgt_gpio5",   "bb_pin": "P8_42", "sys_pin": "P8_36", "sys_reg": "16"},
    6: {"pru_reg": "r31_06", "name": "tgt_gpio6",   "bb_pin": "P8_39", "sys_pin": "P8_34", "sys_reg": "17"},
    7: {"pru_reg": "r31_07", "name": "tgt_uart_rx", "bb_pin": "P8_40", "sys_pin": "P9_26", "sys_reg": "14"},
    8: {"pru_reg": "r31_08", "name": "tgt_uart_tx", "bb_pin": "P8_27", "sys_pin": "P9_24", "sys_reg": "15"},
    9: {"pru_reg": "r31_09", "name": "tgt_bat_ok",  "bb_pin": "P8_29", "sys_pin": "",      "sys_reg": ""},
}
# Note: this table is copied (for hdf5-reference) from pru1/include/hw_config.h
# Note: shepherd-core has gpio-models + data! this lives now in
#       shepherd_core/shepherd_core/data_models/testbed/gpio_fixture.yaml
# fmt: on
