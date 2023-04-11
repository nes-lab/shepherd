import pytest
import pyximport
import sys
sys.path.append('/software/firmware/pru0-cython-module')

from Cvirtual_converter import VirtualConverter

accessVC = VirtualConverter()

def test_div_uV_n4():
	assert accessVC.div_uV_n4(4000000, 2000000) > 0 # To Be Asserted with online values.
	
def test_set_P_input_fW():
	assert accessVC.set_P_input_fW(1000) is not None 
	
def test_set_P_output_fW():
	assert accessVC.set_P_output_fW(1000) is not None 
	
def test_set_V_intermediate_uV():
	assert accessVC.set_V_intermediate_uV(1000) is not None 

def test_get_P_input_fW():
	assert accessVC.get_P_input_fW() is not None 
	
def test_get_P_output_fW():
	assert accessVC.get_P_output_fW() is not None 

def test_get_V_intermediate_uV():
	assert accessVC.get_V_intermediate_uV() is not None 
	
#def test_get_V_intermediate_raw():
#	assert accessVC.get_V_intermediate_raw() is not None 

def test_get_I_mid_out_nA():
	assert accessVC.get_I_mid_out_nA() is not None 
	
def test_get_state_log_intermediate():
	assert accessVC.get_state_log_intermediate() is not None 

def test_converter_update_states_and_output():
	share = {'vsource_skip_gpio_logging': False}
	assert (accessVC.converter_update_states_and_output(share)) is not None

#def test_converter_calc_inp_power():
#	assert (accessVC.converter_calc_inp_power()) > 0

def test_converter_initialize():
	config = {
		'interval_startup_delay_drain_n': 100,
		'V_intermediate_init_uV': 5000000,
		'converter_mode': 1,
		'V_output_uV': 1000000,
		'dV_enable_output_uV': 100000,
		'V_enable_output_threshold_uV': 2000000,
		'V_disable_output_threshold_uV': 1000000
	}

#	assert accessVC.conv_initialize(config) is None
#	accessVC.conv_initialize()
#	assert accessVC.state.V_enable_output_threshold_uV_n32 > 0
#	assert (accessVC.conv_initialize(config)) is not None


#def test_get_input_efficiency_n8():
#	assert accessVC.get_input_efficiency_n8(2, 4) is not None
	
#def test_get_output_inv_efficiency_n4():
#	assert isinstance(accessVC.get_output_inv_efficiency_n4(4294967294), int)
	
