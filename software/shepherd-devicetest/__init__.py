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
from past.builtins import execfile
from shepherd_callbacks import *

#include('../python-package/shepherd/calibration.py')


def main():

    with dpg.window(id="main", label="Shepherd Testing and Debug Tool", width=1000, height=600):

        dpg.add_input_text(id="host_name",
                       #tip="enter name or IP of host",
                       default_value="sheep0",
                       hint="", label="",
                       width=120,
                       )

        dpg.add_same_line(spacing=10)
        dpg.add_button(id="button_disconnect",
                   label="Connect",
                   #tip="Connect or Disconnects to Node",
                   width=150,
                   callback=connect_button_callback)

        dpg.add_same_line(spacing=50)
        dpg.add_text(id="text_section_refresh", default_value="Refresh Rate:")
        dpg.add_same_line(spacing=5)
        dpg.add_input_int(id="refresh_value",
                       #tip="set refresh rate of read-out",
                       default_value=round(1/refresh_interval),
                       label="",
                       width=120,
                       callback=refresh_rate_callback,
                       )

        dpg.add_spacing(count=5)
        dpg.add_text(id="text_section_routing", default_value="Routing")
        dpg.add_text(id="text_section_routing_A", default_value="Board Power")
        dpg.add_same_line(spacing=5)
        dpg.add_radio_button(id="shepherd_pwr",
                         items=[*able_dict],
                         default_value=[*able_dict][1],
                         callback=shepherd_power_callback, show=True)
        dpg.add_same_line(spacing=30)
        dpg.add_text(id="text_section_routing_E", default_value="Shepherd State")
        dpg.add_same_line(spacing=5)
        dpg.add_radio_button(id="shepherd_state",
                         items=[*state_dict],
                         default_value=[*state_dict][1],
                         callback=shepherd_state_callback, show=True,
                         #tip="Sets PRU-Loops to idle or running"
                        )
        dpg.add_same_line(spacing=30)
        dpg.add_text(id="text_section_routing_B", default_value="Target Power")
        dpg.add_same_line(spacing=5)
        dpg.add_radio_button(id="target_pwr",
                         items=[*tgt_dict],
                         default_value=[*tgt_dict][0],
                         callback=target_power_callback, show=True,
                         #tip="Change is also triggering a shepherd state change / pru re-init / reset"
                             )
        dpg.add_same_line(spacing=30)
        dpg.add_text(id="text_section_routing_C", default_value="Target IO")
        dpg.add_same_line(spacing=5)
        dpg.add_radio_button(id="target_io",
                         items=[*tgt_dict],
                         default_value=[*tgt_dict][0],
                         callback=target_io_callback, show=True)
        dpg.add_same_line(spacing=30)
        dpg.add_text(id="text_section_routing_D", default_value="IO Lvl-Conv")
        dpg.add_same_line(spacing=5)
        dpg.add_radio_button(id="io_lvl_converter",
                         items=[*able_dict],
                         default_value=[*able_dict][0],
                         callback=io_level_converter_callback, show=True,
                         #tip="pass through signals from beaglebone to targets"
                             )

        dpg.add_spacing(count=5)
        dpg.add_text(id="text_section_sub", default_value="Control-Logic")

        dpg.add_checkbox(id="gpio_nRes_REC_ADC",
                     #tip="Option to reset this ADC - it has to be reinitialized afterwards (with PRU re-init)",
                     label="Enable Rec-ADC",
                     default_value=True,
                     callback=set_power_state_recoder,
                     )
        dpg.add_same_line(spacing=5)
        dpg.add_checkbox(id="gpio_nRes_EMU_ADC",
                     #tip="Option to reset this ADC - it has to be configured afterwards (with PRU re-init)",
                     label="Enable Emu-ADC",
                     default_value=True,
                     callback=set_power_state_emulator,
                     )
        dpg.add_same_line(spacing=15)
        dpg.add_button(id="button_reinit_prus",
                   label="Re-Init PRUs",
                   #tip="Applies newly received states and configures Cape-ICs",
                   width=130,
                   callback=reinitialize_prus)


        dpg.add_spacing(count=5)
        dpg.add_text(id="text_section_dac", default_value="DAC-Control")

        for iter in range(len(dac_channels)):
            dpg.add_spacing(count=1)
            dpg.add_checkbox(id=f"en_dac{iter}",
                         label="En DAC " + str(iter),
                         default_value=True,
                         callback=dac_en_callback,
                         user_data=iter)
            dpg.add_same_line(spacing=20)
            dpg.add_text(id=f"textA_dac{iter}", default_value="Voltage:")
            dpg.add_same_line(spacing=5)
            dpg.add_slider_int(id=f"value_raw_dac{iter}",
                           #tip="set raw value for dac (ctrl+click for manual input), WARNING: Sliding can crash GUI",
                           #before="Voltage",
                           label="raw",
                           width=450,
                           default_value=0,
                           min_value=0,
                           max_value=((1 << 16) - 1),
                           clamped=True,
                           callback=dac_raw_callback,
                           user_data=iter)
            dpg.add_same_line(spacing=10)
            dpg.add_input_float(id=f"value_mV_dac{iter}",
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
                            user_data=iter)
            dpg.add_same_line(spacing=10)
            dpg.add_text(id=f"textB_dac{iter}", default_value=dac_channels[iter][3])

        dpg.add_spacing(count=5)
        dpg.add_text(id="text_section_adc",
                 default_value="ADC-Readout")

        for iter in range(len(adc_channels)):
            dpg.add_spacing(count=1)
            dpg.add_text(id=f"text_A_adc{iter}", default_value=f"ADC{iter} - " + adc_channels[iter][3])
            dpg.add_same_line(spacing=20)
            dpg.add_text(id=f"text_B_adc{iter}", default_value="raw")
            dpg.add_same_line(spacing=5)
            dpg.add_input_text(id=f"value_raw_adc{iter}",
                           default_value="0",
                           readonly=True,
                           label="",
                           width=200)
            dpg.add_same_line(spacing=20)
            dpg.add_text(id=f"text_C_adc{iter}", default_value="SI")
            dpg.add_same_line(spacing=5)
            dpg.add_input_text(id=f"value_mSI_adc{iter}",
                           default_value="0",
                           readonly=True,
                           label="",
                           width=200)

        dpg.add_spacing(count=5)
        dpg.add_text(id="text_section_gpio",
                 default_value="GPIO-Control")
        dpg.add_spacing(count=1)
        dpg.add_text(id="text_A_gpio", default_value="Set One")
        dpg.add_same_line(spacing=35)
        dpg.add_radio_button(id="gpio_input",
                         items=gpio_channels,
                         callback=gpio_callback,
                         horizontal=True,
                         default_value=len(gpio_channels)-1)

        dpg.add_spacing(count=1)
        dpg.add_text(id="text_B_gpio", default_value="PRU Input")
        dpg.add_same_line(spacing=16)
        dpg.add_input_text(id=f"gpio_output",
                       default_value="0",
                       readonly=True,
                       label="",
                       width=200)

        dpg.add_spacing(count=2)
        dpg.add_text(id="text_C_gpio", default_value="PRU Output")
        dpg.add_same_line(spacing=10)
        dpg.add_checkbox(id="gpio_BAT_OK",
                     label="BAT_OK",
                     default_value=False,
                     callback=gpio_batok_callback,
                     )

    # TODO: restore old dpg v0.6 functionality (v0.8.64 is still missing some pieces, or proper doc) -> also add back tooltips
    #dpg.set_main_window_title(title="Shepherd Testing and Debug Tool")
    #dpg.set_main_window_size(1000, 600)

    #dpg.set_render_callback(callback=window_refresh_callback)
    #dpg.set_viewport_resize_callback(callback=window_refresh_callback)
    #dpg.set_viewport_title(title="Shepherd Testing and Debug Tool (((VIEWPORT)))")
    #dpg.set_theme(theme="Gold")  # fav: Purple, Gold, Light
    dpg.set_start_callback(callback=program_start_callback)


if __name__ == '__main__':
    main()
    dpg.set_primary_window("main", True)
    dpg.start_dearpygui()
    dpg.stop_dearpygui()
