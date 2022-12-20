import sys
# sys.path.append("/vishal/shepherd/software/firmware/pru0-cython-module")
# print(sys.path)
sys.path.append('/software/firmware/pru0-cython-module')
# import pyximport
import numpy as np

from Cvirtual_converter import VirtualConverter

#from shepherd.software.virtual_source_config import VirtualSourceConfig

#vscfg = VirtualSourceConfig()
#vconv = VirtualConverter(vscfg.export_for_sysfs())

#x = int(0)
#print(VirtualConverter.get_I_mid_out_nA())
#print(VirtualConverter.converter_calc_inp_power(5, 6))
#print(VirtualConverter.converter_initialize(0))

class Test():
	def __init__(self, access):
		self.access = access
		
	def Test_Method1(self):
		return self.access.get_V_intermediate_uV()
		
	def Test_Method2(self):
		return self.access.get_P_input_fW() 
		
	def Test_Method3(self):
		return self.access.get_P_output_fW() 
		
	def Test_Method4(self):
		return self.access.get_I_mid_out_nA() 
	
	def Test_Method5(self):
		return self.access.get_input_efficiency_n8(self, 2, 4) 
		
	def Test_Method6(self):
		return self.access.get_output_inv_efficiency_n4(self, -4)
		
	def Test_Method7(self):
		return self.access.div_uV_n4(self, 100000, 2000000)
		
if __name__ == "__main__":    
	TempList = list(np.random.randint(low = 0, high=9, size=25))

	accessVC = VirtualConverter(TempList)
	accessInstanceTest=Test(accessVC)

	print(accessInstanceTest.Test_Method1())
	print(accessInstanceTest.Test_Method2())
	print(accessInstanceTest.Test_Method3())
	print(accessInstanceTest.Test_Method4())
	print(accessInstanceTest.Test_Method5())	# for get_input_efficiency_n8()
	print(accessInstanceTest.Test_Method6())	# for get_output_inv_efficiency_n4()
	print(accessInstanceTest.Test_Method7())	# for div_uV_n4()
    
    
