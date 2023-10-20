"""
shepherd.commons
~~~~~
Defines details of the data exchange protocol between PRU0 and the python code.
The various parameters need to be the same on both sides. Refer to the
corresponding implementation in `software/firmware/include/commons.h`

:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
MAX_GPIO_EVT_PER_BUFFER = 16_384  # 2^14
# TODO: replace by (currently non-existing) sysfs_interface

MSG_BUF_FROM_HOST = 0x01
MSG_BUF_FROM_PRU = 0x02

MSG_PGM_ERROR_WRITE = 0x93  # val0: addr, val1: data
MSG_PGM_ERROR_VERIFY = 0x94  # val0: addr, val1: data(original)
MSG_PGM_ERROR_PARSE = 0x96  # val0: ihex_return

MSG_DBG_ADC = 0xA0
MSG_DBG_DAC = 0xA1
MSG_DBG_GPI = 0xA2
MSG_DBG_GP_BATOK = 0xA3
MSG_DBG_PRINT = 0xA6

MSG_DBG_VSRC_P_INP = 0xA8
MSG_DBG_VSRC_P_OUT = 0xA9
MSG_DBG_VSRC_V_CAP = 0xAA
MSG_DBG_VSRC_V_OUT = 0xAB
MSG_DBG_VSRC_INIT = 0xAC
MSG_DBG_VSRC_CHARGE = 0xAD
MSG_DBG_VSRC_DRAIN = 0xAE
MSG_DBG_FN_TESTS = 0xAF
MSG_DBG_VSRC_HRV_P_INP = 0xB1

MSG_DEP_ERR_INCMPLT = 0xE3
MSG_DEP_ERR_INVLDCMD = 0xE4
MSG_DEP_ERR_NOFREEBUF = 0xE5

# fmt: off
# ruff: noqa: E241, E501
GPIO_LOG_BIT_POSITIONS = {
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
# Note: this table is copied (for hdf5-reference) from pru1/main.c, HW-Rev2.4b
# Note: datalib has gpio-models + data! this lives now in
#       shepherd_core/shepherd_core/data_models/testbed/gpio_fixture.yaml
# fmt: on
