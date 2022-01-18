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
pru_reg     name            BB_pin	sys_pin
r31_00      TARGET_GPIO0    P8_45	P8_14, g0[14]
r31_01      TARGET_GPIO1    P8_46	P8_17, g0[27]
r31_02      TARGET_GPIO2    P8_43	P8_16, g1[14]
r31_03      TARGET_GPIO3    P8_44	P8_15, g1[15]
r31_04      TARGET_GPIO4    P8_41	P8_26, g1[29]
r31_05      TARGET_GPIO5    P8_42	P8_36, g2[16]
r31_06      TARGET_GPIO6    P8_39	P8_34, g2[17]
r31_07      TARGET_UART_RX  P8_40	P9_26, g0[14]
r31_08      TARGET_UART_TX  P8_27	P9_24, g0[15]
r30_09/out  TARGET_BAT_OK   P8_29	-
"""
# Note: this table is copied (for hdf5-reference) from pru1/main.c
