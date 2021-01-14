# -*- coding: utf-8 -*-

"""
shepherd.calibration_default
~~~~~
Contains some info about the hardware configuration on the shepherd
cape. Based on these values, one can derive the expected adc readings given
an input voltage/current or, for emulation, the expected voltage and current
given the digital code in the DAC.


:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""

# both current channels have a 0.1 % shunt resistance of
R_SHT = 1.00  # [ohm]
# the instrumentation amplifiers are configured for gain of
G_INST_AMP = 100 # [n]
# we use the ADC's internal reference with
V_REF_ADC = 4.096  # [V]
# range of current channels is
G_ADC_I = 1.25  # [gain / V_REF]
# range of voltage channels is
G_ADC_V = 1.25  # [gain / V_REF]
# bit resolution of ADC
M_ADC = 18  # [bit]
# DACs use internal reference with
V_REF_DAC = 2.5  # [V]
# gain of DAC-CH-A is set to
G_DAC_A = 2  # [n]
# gain of DAC-CH-B is set to
G_DAC_B = 2  # [n]
# bit resolution of DAC
M_DAC = 16  # [bit]


def current_to_adc(current: float):
    # voltage on input of adc
    v_adc = G_INST_AMP * R_SHT * current
    # digital value according to ADC gain
    return v_adc * (2 ** M_ADC) / (G_ADC_I * V_REF_ADC)


def adc_to_current(i_adc: float):
    # voltage on input of adc
    v_adc = i_adc * (G_ADC_I * V_REF_ADC) / (2 ** M_ADC)
    # current according to adc value
    return v_adc / (R_SHT * G_INST_AMP)


def voltage_to_adc(voltage: float):
    # digital value according to ADC gain
    return voltage * (2 ** M_ADC) / (G_ADC_V * V_REF_ADC)


def adc_to_voltage(v_adc: float):
    # voltage according to ADC value
    return v_adc * (G_ADC_V * V_REF_ADC) / (2 ** M_ADC)


def dac_to_voltage_ch_a(value: int):
    return float(value) * (V_REF_DAC * G_DAC_A) / (2 ** M_DAC)


def voltage_to_dac_ch_a(voltage: float):
    return voltage * (2 ** M_DAC) / (V_REF_DAC * G_DAC_A)


def dac_to_voltage_ch_b(value: int):
    return float(value) * (V_REF_DAC * G_DAC_B) / (2 ** M_DAC)


def voltage_to_dac_ch_b(voltage: float):
    return voltage * (2 ** M_DAC) / (V_REF_DAC * G_DAC_B)
