import pytest
import pyximport
import sys
sys.path.append('/software/firmware/pru0-cython-module')
# print(sys.path)

from Cvirtual_converter import VirtualConverter

accessVC = VirtualConverter()

def test_get_V_intermediate_uV():
	assert accessVC.get_V_intermediate_uV() == 0
	
def test_get_P_input_fW():
	assert accessVC.get_P_input_fW() == 0
		
def test_get_P_output_fW():
	assert accessVC.get_P_output_fW() == 0
	
def test_get_I_mid_out_nA():
	assert accessVC.get_I_mid_out_nA() < 5000000000

def test_get_input_efficiency_n8():
	assert accessVC.get_input_efficiency_n8(2, 4) > 1
	
def test_get_output_inv_efficiency_n4():
	assert accessVC.get_output_inv_efficiency_n4( -4) < 1
	
def test_div_uV_n4():
	assert accessVC.div_uV_n4(100000, 2000000) > 100

#if __name__ == "__main__":    
#	accessVC = VirtualConverter()
#	test_get_V_intermediate_uV()
	
#def test_addition():
#   assert 1 + 1 == 2

#def test_substract():
#    assert 1 - 1 == 0
