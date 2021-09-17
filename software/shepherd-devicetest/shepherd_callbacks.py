from typing import NoReturn
import os
import zerorpc
import dearpygui.dearpygui as dpg
from past.builtins import execfile
import time

def include(filename):
    if os.path.exists(filename):
        execfile(filename)
    else:
        os.error(f"File {filename} not found")


#include('../python-package/shepherd/calibration.py')

###############################
# Basic Window Callbacks
###############################

refresh_interval = 0.25  # s
refresh_next = 0

def program_start_callback(sender, data) -> NoReturn:
    update_gui_elements()
    print("Program started")


def window_refresh_callback(sender, data) -> NoReturn:
    global refresh_next, refresh_interval
    ts = time.time()
    if ts < refresh_next:
        return

    refresh_next = ts + refresh_interval
    global shepherd_io, shepherd_state
    if (shepherd_io is not None) and (shepherd_state is True):
        gpio_refresh()
        adc_refresh()


def update_gui_elements() -> NoReturn:
    # TODO: DPG 0.8.x has trouble disabling items - it does not work - and text-elements even panic
    global shepherd_io, shepherd_state, state_dict
    host_state = shepherd_io is not None
    shepherd_state = state_dict[dpg.get_value("shepherd_state")]
    dpg.configure_item("host_name", enabled=not host_state)
    dpg.configure_item("button_disconnect", label="Disconnect from Host" if host_state else "Connect to Host")
    dpg.configure_item("refresh_value", enabled=host_state)
    dpg.configure_item("shepherd_pwr", enabled=host_state)
    dpg.configure_item("shepherd_state", enabled=host_state)
    dpg.configure_item("target_pwr", enabled=host_state)  # and not shepherd_state
    dpg.configure_item("target_io", enabled=host_state)
    dpg.configure_item("io_lvl_converter", enabled=host_state)

    dpg.configure_item("gpio_nRes_REC_ADC", enabled=host_state)
    dpg.configure_item("gpio_nRes_EMU_ADC", enabled=host_state)
    dpg.configure_item("button_reinit_prus", enabled=host_state)
    # TODO: more items
    for iter in range(len(dac_channels)):
        dac_state = dpg.get_value(f"en_dac{iter}") and host_state
        dpg.configure_item(f"en_dac{iter}", enabled=host_state)
        #dpg.configure_item(f"textA_dac{iter}", enabled=dac_state)  #
        #dpg.configure_item(f"textB_dac{iter}", enabled=dac_state)
        dpg.configure_item(f"value_raw_dac{iter}", enabled=dac_state)
        dpg.configure_item(f"value_mV_dac{iter}", enabled=dac_state)
    for iter in range(len(adc_channels)):
        dpg.configure_item(f"value_raw_adc{iter}", enabled=host_state)
        dpg.configure_item(f"value_mSI_adc{iter}", enabled=host_state)
    dpg.configure_item("gpio_input", enabled=host_state)
    dpg.configure_item("gpio_BAT_OK", enabled=host_state)
    dpg.configure_item("gpio_output", enabled=host_state)


def refresh_rate_callback(sender, element_data, user_data) -> NoReturn:
    global refresh_interval
    refresh_interval = round(1.0 / float(element_data), 3)
    print(f"Wished for {element_data} fps, {refresh_interval} s")

########################
# Zero RPC Connection
########################


shepherd_io = None
shepherd_cal = None
shepherd_state = True


def connect_to_node(host: str):
    # todo: could also use fabric/connection to start rpc server on node
    rpc_client = zerorpc.Client(timeout=60, heartbeat=20)
    rpc_client.connect(f"tcp://{host}:4242")

    # This replaces
    # shepherd_io = ShepherdDebug()
    # shepherd_io.__enter__()
    if check_connection(rpc_client):
        return rpc_client
    else:
        return None


def check_connection(rpc_client=None) -> bool:
    if rpc_client is None:
        global shepherd_io
        rpc_client = shepherd_io
    if rpc_client is None:
        return False
    try:
        rpc_client.is_alive()
    except zerorpc.exceptions.RemoteError:
        return False
    return True


def connect_button_callback(sender, element_data, user_data) -> NoReturn:
    global shepherd_io, shepherd_cal
    host = dpg.get_value("host_name")
    if shepherd_io is None:
        shepherd_io = connect_to_node(host)
    else:
        shepherd_io = None
        print(f"Disconnected from Host '{host}'")
    if check_connection():
        print(f"Connected to Host '{host}'")
        #shepherd_cal = shepherd_io._cal.from_default()
    update_gui_elements()

#################################
# Board (Power)-Routing
#################################


state_dict = {"Stop": False, "Running": True}
able_dict = {"Disabled": False, "Enabled": True}
tgt_dict = {"Target A": True, "Target B": False}


def shepherd_power_callback(sender, element_data, user_data) -> NoReturn:
    global shepherd_io, able_dict
    shepherd_io.set_shepherd_pcb_power(able_dict[element_data])


def shepherd_state_callback(sender, element_data, user_data) -> NoReturn:
    global shepherd_io, shepherd_state, state_dict
    shepherd_state = state_dict[element_data]
    shepherd_io.set_shepherd_state(shepherd_state)
    update_gui_elements()


def target_power_callback(sender, element_data, user_data) -> NoReturn:
    global shepherd_io, tgt_dict
    sel_a = tgt_dict[element_data]
    shepherd_io.select_target_for_power_tracking(sel_a)


def target_io_callback(sender, element_data, user_data) -> NoReturn:
    global shepherd_io, tgt_dict
    sel_a = tgt_dict[element_data]
    shepherd_io.select_target_for_io_interface(sel_a)


def io_level_converter_callback(sender, element_data, user_data) -> NoReturn:
    global shepherd_io, able_dict
    state = able_dict[element_data]
    shepherd_io.set_io_level_converter(state)


def set_power_state_emulator(sender, en_state, user_data) -> NoReturn:
    global shepherd_io
    shepherd_io.set_power_state_emulator(en_state)


def set_power_state_recoder(sender, en_state, user_data) -> NoReturn:
    global shepherd_io
    shepherd_io.set_power_state_recoder(en_state)


def reinitialize_prus(sender, element_data, user_data) -> NoReturn:
    global shepherd_io, shepherd_state
    shepherd_io.reinitialize_prus()
    shepherd_io.set_shepherd_state(shepherd_state)

#################################
# DAC functionality
#################################


dac_channels = [  # combination of debug channel number, voltage_index, cal_component, cal_channel
    [1, "harvesting", "dac_voltage_a", "Harvester VSimBuf"],
    [2, "harvesting", "dac_voltage_b", "Harvester VMatching"],
    [4, "emulation", "dac_voltage_a", "Emulator Rail A"],
    [8, "emulation", "dac_voltage_b", "Emulator Rail B"], ]


def dac_en_callback(sender, en_state, iter) -> NoReturn:
    global shepherd_io, dac_channels
    value = dpg.get_value(f"value_raw_dac{iter}") if en_state else 0
    shepherd_io.dac_write(dac_channels[iter], value)
    update_gui_elements()


def dac_raw_callback(sender, value_raw, iter) -> NoReturn:
    global shepherd_io, dac_channels
    dac_cfg = dac_channels[iter]
    value_si = shepherd_io.convert_raw_to_value(dac_cfg[1], dac_cfg[2], value_raw)
    value_si = round(value_si * 10**3, 3)
    dpg.set_value(f"value_mV_dac{iter[0]}", value_si)
    shepherd_io.dac_write(dac_cfg[0], value_raw)


def dac_val_callback(sender, value_mV, iter) -> NoReturn:
    global shepherd_io, dac_channels
    dac_cfg = dac_channels[iter]
    value_raw = shepherd_io.convert_value_to_raw(dac_cfg[1], dac_cfg[2], value_mV / 1e3)
    dpg.set_value(f"value_raw_dac{iter}", value_raw)
    shepherd_io.dac_write(dac_cfg[0], value_raw)


#################################
# ADC functionality
#################################

adc_channels = [  # combination of debug channel name, cal_component, cal_channel
    ("hrv_i_in", "harvesting", "adc_current", "Harvester I_in [mA]"),
    ("hrv_v_in", "harvesting", "adc_voltage", "Harvester V_in [mV]"),
    ("emu_i_out", "emulation", "adc_current", "Emulator I_out [mA]"), ]


def adc_refresh() -> NoReturn:
    global shepherd_io
    for iter in range(len(adc_channels)):
        adc_cfg = adc_channels[iter]
        value_raw = shepherd_io.adc_read(adc_cfg[0])
        value_si = shepherd_io.convert_raw_to_value(adc_cfg[1], adc_cfg[2], value_raw)
        value_si = round(value_si * 10**3, 4)
        dpg.set_value(f"value_raw_adc{iter}", str(value_raw))
        dpg.set_value(f"value_mSI_adc{iter}", str(value_si))


#################################
# GPIO functionality
#################################

gpio_channels = [str(val) for val in list(range(9)) + ["None"]]


def gpio_refresh() -> NoReturn:
    global shepherd_io
    value = shepherd_io.gpi_read()
    dpg.set_value("gpio_output", value)
    # print(f"refreshed {value}")


def gpio_callback(sender, element_data, user_data) -> NoReturn:
    global shepherd_io
    value = gpio_channels.index(element_data)
    shepherd_io.set_gpio_one_high(value)
    gpio_refresh()


def gpio_batok_callback(sender, en_state, user_data) -> NoReturn:
    global shepherd_io
    shepherd_io.gp_set_batok(en_state)
    gpio_refresh()


"""
cal = CalibrationData.from_default()
shepherd_io.set_aux_target_voltage(cal, 3.3)
shepherd_io.set_target_io_level_conv(True)
shepherd_io.select_main_target_for_io(False)
shepherd_io.select_main_target_for_power(True)
shepherd_io.start()

target_gpio = TargetIO()
target_gpio.pin_count
target_gpio.one_high(index)

voltage_raw = cal.convert_value_to_raw(cal_comp, cal_ch, dac_voltages[v_index])
shepherd_io.dac_write(dbg_ch, voltage_raw)

value_raw = shepherd_io.adc_read(dbg_ch)
value_si = cal.convert_raw_to_value(cal_comp, cal_ch, value_raw) * 1e3

gpi_state = shepherd_io.gpi_read()

shepherd_io._cleanup()

## other useful stuff

_set_shepherd_pcb_power

"""


def filter_update_callback(sender, element_data, user_data) -> NoReturn:
    print("filter_update_callback")
    # update_table()


def update_buttons() -> NoReturn:
    print("update_buttons")


def update_button_callback(sender, element_data, user_data) -> NoReturn:
    print("update_button_callback")


def save_button_callback(sender, element_data, user_data) -> NoReturn:
    print("connect_button_callback")
