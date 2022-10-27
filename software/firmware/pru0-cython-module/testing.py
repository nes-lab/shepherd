# import sys
# print(sys.path)
# sys.path.append('/home/vishal/shepherd/software/firmware/pru0-cython-module')
# import pyximport

from virtual_converter import VirtualConverter

from shepherd.virtual_source_config import VirtualSourceConfig

vscfg = VirtualSourceConfig()
vconv = VirtualConverter(vscfg.export_for_sysfs())

x = int(0)
print(vconv.converter_calc_out_power(x))
print(vconv.converter_calc_inp_power(5, 6))
