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
MAX_GPIO_EVT_PER_BUFFER = 16_384  # 2^14
FIFO_BUFFER_SIZE = 64   # keep in sync with kernel-module and pru-firmware

ADC_SAMPLES_PER_BUFFER = 10_000
BUFFER_PERIOD_NS = 100_000_000
SAMPLE_INTERVAL_NS = BUFFER_PERIOD_NS // ADC_SAMPLES_PER_BUFFER
SAMPLE_INTERVAL_US = SAMPLE_INTERVAL_NS // 1000

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
pru_reg     name            linux_pin
r31_00      TARGET_GPIO0    P8_45
r31_01      TARGET_GPIO1    P8_46
r31_02      TARGET_SWD_CLK  P8_43
r31_03      TARGET_SWD_IO   P8_44
r31_04      TARGET_UART_TX  P8_41
r31_05      TARGET_UART_RX  P8_42
r31_06      TARGET_GPIO2    P8_39
r31_07      TARGET_GPIO3    P8_40
r31_08      TARGET_GPIO4    P8_27
r30_09/out  TARGET_BAT_OK   P8_29
"""
# Note: this table is copied (for hdf5-reference) from pru1/main.c
