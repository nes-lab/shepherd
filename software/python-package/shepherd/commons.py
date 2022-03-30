# -*- coding: utf-8 -*-

"""
shepherd.commons
~~~~~
Defines details of the data exchange protocol between PRU0 and the python code.
The various parameters need to be the same on both sides. Refer to the
corresponding implementation in `software/firmware/include/commons.h`

:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
MAX_GPIO_EVT_PER_BUFFER = 16_384  # 2^14  # TODO: replace by (currently non-existing) sysfs_interface

MSG_BUF_FROM_HOST = 0x01
MSG_BUF_FROM_PRU = 0x02

MSG_DBG_ADC = 0xA0
MSG_DBG_DAC = 0xA1
MSG_DBG_GPI = 0xA2
MSG_DBG_GP_BATOK = 0xA3
MSG_DBG_PRINT = 0xA6

MSG_DBG_VSOURCE_P_INP = 0xA8
MSG_DBG_VSOURCE_P_OUT = 0xA9
MSG_DBG_VSOURCE_V_CAP = 0xAA
MSG_DBG_VSOURCE_V_OUT = 0xAB
MSG_DBG_VSOURCE_INIT = 0xAC
MSG_DBG_VSOURCE_CHARGE = 0xAD
MSG_DBG_VSOURCE_DRAIN = 0xAE
MSG_DBG_FN_TESTS = 0xAF

MSG_DEP_ERR_INCMPLT = 0xE3
MSG_DEP_ERR_INVLDCMD = 0xE4
MSG_DEP_ERR_NOFREEBUF = 0xE5

GPIO_LOG_BIT_POSITIONS = """
pru_reg     BB_pin	name            sys_pin gpio
r31_00      P8_45	TARGET_GPIO0    P8_14   r0[14]
r31_01      P8_46	TARGET_GPIO1    P8_17   r0[27]
r31_02      P8_43	TARGET_SWD_CLK  P9_17   r0[5]
r31_03      P8_44	TARGET_SWD_IO   P9_18   r0[4]
r31_04      P8_41	TARGET_UART_TX  P9_24   r0[15]
r31_05      P8_42	TARGET_UART_RX  P9_26   r0[14]
r31_06      P8_39	TARGET_GPIO2    P8_16   r1[14]
r31_07      P8_40	TARGET_GPIO3    P8_15   r1[15]
r31_08      P8_27	TARGET_GPIO4    P8_26   r1[29]
r30_09/out  P8_29	TARGET_BAT_OK   -       -
"""
# Note: this table is copied (for hdf5-reference) from pru1/main.c
