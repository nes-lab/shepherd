"""
shepherd_testing_gui
~~~~~
dearPyGui-based debug and test utility for controlling hw-functions of a shepherd node
remotely.

:copyright: (c) 2021 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
import dearpygui.dearpygui as dpg

from .shepherd_callbacks import *

# include('../python-package/shepherd/calibration.py')
# changes to make 0.8-Code work with v1.3
# - replace .add_same_line(spacing=..) with "with dpg.group: ....... dpg.add_spacer(..)
# - id= is now tag=


def assemble_window():

    with dpg.window(
        tag="main", label="Shepherd Testing and Debug Tool", width=1000, height=600
    ):

        with dpg.group(horizontal=True):
            dpg.add_input_text(
                tag="host_name", default_value="sheep0", hint="", label="", width=120
            )
            with dpg.tooltip("host_name"):
                dpg.add_text("enter name or IP of host")

            dpg.add_spacer(width=10)
            dpg.add_button(
                tag="button_disconnect",
                label="Connect",
                width=150,
                callback=connect_button_callback,
            )
            with dpg.tooltip("button_disconnect"):
                dpg.add_text("Connect or Disconnects to Node")

            dpg.add_spacer(width=50)
            dpg.add_text(tag="text_section_refresh", default_value="Refresh Rate:")
            dpg.add_spacer(width=5)
            dpg.add_input_int(
                tag="refresh_value",
                default_value=round(1 / refresh_interval),
                label="",
                width=120,
                callback=refresh_rate_callback,
            )
            with dpg.tooltip("refresh_value"):
                dpg.add_text("set refresh rate of read-out")

        dpg.add_spacer(height=5)
        dpg.add_text(tag="text_section_routing", default_value="Routing")

        with dpg.group(horizontal=True):
            dpg.add_text(tag="text_section_routing_A", default_value="Board Power")
            dpg.add_radio_button(
                tag="shepherd_pwr",
                items=[*able_dict],
                default_value=[*able_dict][1],
                callback=shepherd_power_callback,
                show=True,
            )
            dpg.add_spacer(width=10)
            dpg.add_text(tag="text_section_routing_E", default_value="Shepherd State")
            dpg.add_radio_button(
                tag="shepherd_state",
                items=[*state_dict],
                default_value=[*state_dict][1],
                callback=shepherd_state_callback,
                show=True,
            )
            with dpg.tooltip("shepherd_state"):
                dpg.add_text("Sets PRU-Loops to idle or running")
            dpg.add_spacer(width=10)
            dpg.add_text(tag="text_section_routing_B", default_value="Target Power")
            dpg.add_radio_button(
                tag="target_pwr",
                items=[*tgt_dict],
                default_value=[*tgt_dict][0],
                callback=target_power_callback,
                show=True,
            )
            with dpg.tooltip("target_pwr"):
                dpg.add_text(
                    "Change is also triggering a shepherd state change / pru re-init / reset"
                )
            dpg.add_spacer(width=10)
            dpg.add_text(tag="text_section_routing_C", default_value="Target IO")
            dpg.add_radio_button(
                tag="target_io",
                items=[*tgt_dict],
                default_value=[*tgt_dict][0],
                callback=target_io_callback,
                show=True,
            )
            dpg.add_spacer(width=10)
            dpg.add_text(tag="text_section_routing_D", default_value="IO Lvl-Conv")
            dpg.add_radio_button(
                tag="io_lvl_converter",
                items=[*able_dict],
                default_value=[*able_dict][0],
                callback=io_level_converter_callback,
                show=True,
            )
            with dpg.tooltip("io_lvl_converter"):
                dpg.add_text("pass through signals from beaglebone to targets")

        dpg.add_spacer(height=5)
        dpg.add_text(tag="text_section_sub", default_value="Control-Logic")

        with dpg.group(horizontal=True):
            dpg.add_checkbox(
                tag="gpio_nRes_REC_ADC",
                label="Enable Rec-ADC",
                default_value=True,
                callback=set_power_state_recoder,
            )
            with dpg.tooltip("gpio_nRes_REC_ADC"):
                dpg.add_text(
                    "Option to reset this ADC - it has to be reinitialized afterwards (with PRU re-init)"
                )
            dpg.add_spacer(width=5)

            dpg.add_checkbox(
                tag="gpio_nRes_EMU_ADC",
                label="Enable Emu-ADC",
                default_value=True,
                callback=set_power_state_emulator,
            )
            with dpg.tooltip("gpio_nRes_EMU_ADC"):
                dpg.add_text(
                    "Option to reset this ADC - it has to be configured afterwards (with PRU re-init)"
                )
            dpg.add_spacer(width=15)

            dpg.add_button(
                tag="button_reinit_prus",
                label="Re-Init PRUs",
                width=130,
                callback=reinitialize_prus,
            )
            with dpg.tooltip("button_reinit_prus"):
                dpg.add_text("Applies newly received states and configures Cape-ICs")

        dpg.add_spacer(height=5)
        dpg.add_text(tag="text_section_dac", default_value="DAC-Control")

        for _iter, _vals in enumerate(dac_channels):
            dpg.add_spacer(height=1)
            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    tag=f"en_dac{_iter}",
                    label="En DAC " + str(_iter),
                    default_value=True,
                    callback=dac_en_callback,
                    user_data=_iter,
                )
                dpg.add_spacer(width=10)
                dpg.add_text(tag=f"textA_dac{_iter}", default_value="Voltage:")
                dpg.add_slider_int(
                    tag=f"value_raw_dac{_iter}",
                    label="raw",
                    width=400,
                    default_value=0,
                    min_value=0,
                    max_value=((1 << 16) - 1),
                    clamped=True,
                    callback=dac_raw_callback,
                    user_data=_iter,
                )
                with dpg.tooltip(f"value_raw_dac{_iter}"):
                    dpg.add_text("set raw value for dac (ctrl+click for manual input)")
                dpg.add_spacer(width=10)
                dpg.add_input_float(
                    tag=f"value_mV_dac{_iter}",
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
                    user_data=_iter,
                )
                dpg.add_spacer(width=10)
                dpg.add_text(tag=f"textB_dac{_iter}", default_value=_vals[3])

        dpg.add_spacer(height=5)
        dpg.add_text(tag="text_section_adc", default_value="ADC-Readout")

        for _iter, _vals in enumerate(adc_channels):
            dpg.add_spacer(height=1)
            with dpg.group(horizontal=True):
                dpg.add_text(
                    tag=f"text_A_adc{_iter}", default_value=f"ADC{_iter} - " + _vals[3]
                )
                dpg.add_spacer(width=20)
                dpg.add_text(tag=f"text_B_adc{_iter}", default_value="raw")
                dpg.add_spacer(width=2)
                dpg.add_input_text(
                    tag=f"value_raw_adc{_iter}",
                    default_value="0",
                    readonly=True,
                    label="",
                    width=200,
                )
                dpg.add_spacer(width=20)
                dpg.add_text(tag=f"text_C_adc{_iter}", default_value="SI")
                dpg.add_spacer(width=2)
                dpg.add_input_text(
                    tag=f"value_mSI_adc{_iter}",
                    default_value="0",
                    readonly=True,
                    label="",
                    width=200,
                )

        dpg.add_spacer(height=5)
        dpg.add_text(tag="text_section_gpio", default_value="GPIO-Control")
        dpg.add_spacer(height=1)

        with dpg.group(horizontal=True):
            dpg.add_text(tag="text_A_gpio", default_value="Set One")
            dpg.add_spacer(width=35)
            dpg.add_radio_button(
                tag="gpio_input",
                items=gpio_channels,
                callback=gpio_callback,
                horizontal=True,
                default_value=len(gpio_channels) - 1,
            )

        dpg.add_spacer(height=1)
        with dpg.group(horizontal=True):
            dpg.add_text(tag="text_B_gpio", default_value="PRU Input")
            dpg.add_spacer(width=16)
            dpg.add_input_text(
                tag=f"gpio_output",
                default_value="0",
                readonly=True,
                label="",
                width=200,
            )

        dpg.add_spacer(height=2)
        with dpg.group(horizontal=True):
            dpg.add_text(tag="text_C_gpio", default_value="PRU Output")
            dpg.add_spacer(width=10)
            dpg.add_checkbox(
                tag="gpio_BAT_OK",
                label="BAT_OK",
                default_value=False,
                callback=gpio_batok_callback,
            )

    # TODO: restore old dpg v0.6 functionality (v0.8.64 is still missing themes)
    # dpg.set_theme(theme="Gold")  # fav: Purple, Gold, Light
    dpg.set_frame_callback(frame=1, callback=program_start_callback)
    dpg.set_frame_callback(frame=10, callback=window_refresh_callback)
    dpg.configure_item("refresh_value", enabled=False)


if __name__ == "__main__":
    dpg.create_context()
    dpg.create_viewport(
        title="Shepherd Testing and Debug Tool (VP)", width=1000, height=600
    )
    dpg.setup_dearpygui()

    assemble_window()
    dpg.set_primary_window("main", True)

    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()
