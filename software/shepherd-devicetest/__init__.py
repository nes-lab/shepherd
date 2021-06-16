# -*- coding: utf-8 -*-

"""
shepherd_testing_gui
~~~~~
dearPyGui-based debug and test utility for controlling hw-functions of a shepherd node
remotely.

:copyright: (c) 2021 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import os
from dearpygui.core import *
from dearpygui.simple import *
from past.builtins import execfile
from shepherd_callbacks import *

#include('../python-package/shepherd/calibration.py')


def main():

    set_main_window_title(title="Shepherd Testing and Debug Tool")
    set_main_window_size(1000, 600)
    set_render_callback(callback=window_refresh_callback)
    set_theme(theme="Gold")  # fav: Purple, Gold, Light
    set_start_callback(callback=program_start_callback)

    with window("main"):

        add_input_text("host_name",
                       tip="enter name or IP of host",
                       default_value="sheep0",
                       hint="", label="",
                       width=120,
                       )

        add_same_line(spacing=10)
        add_button("button_disconnect",
                   label="Connect",
                   tip="Connect or Disconnects to Node",
                   width=150,
                   callback=connect_button_callback)

        add_same_line(spacing=50)
        add_text("text_section_refresh", default_value="Refresh Rate:")
        add_same_line(spacing=5)
        add_input_int("refresh_value",
                       tip="set refresh rate of read-out",
                       default_value=round(1/refresh_interval),
                       label="",
                       width=120,
                       callback=refresh_rate_callback,
                       )

        add_spacing(count=5)
        add_text("text_section_routing", default_value="Routing")
        add_text("text_section_routing_A", default_value="Board Power")
        add_same_line(spacing=5)
        add_radio_button("shepherd_pwr",
                         items=["Disabled", "Enabled"],
                         default_value=1,
                         callback=shepherd_power_callback, show=True)
        add_same_line(spacing=30)
        add_text("text_section_routing_E", default_value="Shepherd State")
        add_same_line(spacing=5)
        add_radio_button("shepherd_state",
                         items=["Stop", "Running"],
                         default_value=1,
                         callback=shepherd_state_callback, show=True)
        add_same_line(spacing=30)
        add_text("text_section_routing_B", default_value="Target Power")
        add_same_line(spacing=5)
        add_radio_button("target_pwr",
                         items=["Target A", "Target B"],
                         default_value=1,
                         callback=target_power_callback, show=True)
        add_same_line(spacing=30)
        add_text("text_section_routing_C", default_value="Target IO")
        add_same_line(spacing=5)
        add_radio_button("target_io",
                         items=["Target A", "Target B"],
                         default_value=1,
                         callback=target_io_callback, show=True)
        add_same_line(spacing=30)
        add_text("text_section_routing_D", default_value="IO Lvl-Conv")
        add_same_line(spacing=5)
        add_radio_button("io_lvl_converter",
                         items=["Disabled", "Enabled"],
                         default_value=0,
                         callback=io_level_converter_callback, show=True)


        add_spacing(count=5)
        add_text("text_section_dac", default_value="DAC-Control")

        for iter in range(len(dac_channels)):
            add_spacing(count=1)
            add_checkbox(f"en_dac{iter}",
                         label="En DAC " + str(iter),
                         default_value=True,
                         callback=dac_en_callback,
                         callback_data=[iter])
            add_same_line(spacing=20)
            add_text(f"textA_dac{iter}", default_value="Voltage:")
            add_same_line(spacing=5)
            add_slider_int(f"value_raw_dac{iter}",
                           tip="set raw value for dac (ctrl+click for manual input)",
                           #before="Voltage",
                           label="raw",
                           width=450,
                           default_value=0,
                           min_value=0,
                           max_value=((1 << 16) - 1),
                           clamped=True,
                           callback=dac_raw_callback,
                           callback_data=[iter])
            add_same_line(spacing=10)
            add_input_float(f"value_mV_dac{iter}",
                            min_value=0.0,
                            max_value=5000.0,
                            min_clamped=True,
                            max_clamped=True,
                            step_fast=100.0,
                            step=10.0,
                            width=150,
                            before="",
                            label="mV",
                            callback=dac_val_callback,
                            callback_data=[iter])
            add_same_line(spacing=10)
            add_text(f"textB_dac{iter}", default_value=dac_channels[iter][3])

        add_spacing(count=5)
        add_text("text_section_adc",
                 default_value="ADC-Readout")

        for iter in range(len(adc_channels)):
            add_spacing(count=1)
            add_text(f"text_A_adc{iter}", default_value=f"ADC{iter} - " + adc_channels[iter][3])
            add_same_line(spacing=20)
            add_text(f"text_B_adc{iter}", default_value="raw")
            add_same_line(spacing=5)
            add_input_text(f"value_raw_adc{iter}",
                           default_value="0",
                           readonly=True,
                           label="",
                           width=200)
            add_same_line(spacing=20)
            add_text(f"text_C_adc{iter}", default_value="SI")
            add_same_line(spacing=5)
            add_input_text(f"value_mSI_adc{iter}",
                           default_value="0",
                           readonly=True,
                           label="",
                           width=200)

        add_spacing(count=5)
        add_text("text_section_gpio",
                 default_value="GPIO-Control")
        add_spacing(count=1)
        add_text("text_A_gpio", default_value="Set One")
        add_same_line(spacing=35)
        add_radio_button("gpio_input",
                         items=gpio_channels,
                         callback=gpio_callback,
                         horizontal=True,
                         default_value=len(gpio_channels)-1)

        add_spacing(count=1)
        add_text("text_B_gpio", default_value="PRU Input")
        add_same_line(spacing=16)
        add_input_text(f"gpio_output",
                       default_value="0",
                       readonly=True,
                       label="",
                       width=200)

        add_spacing(count=2)
        add_text("text_C_gpio", default_value="PRU Output")
        add_same_line(spacing=10)
        add_checkbox("gpio_BAT_OK",
                     label="BAT_OK",
                     default_value=False,
                     callback=gpio_batok_callback,
                     )

if __name__ == '__main__':
    main()
    start_dearpygui(primary_window="main")
    stop_dearpygui()
