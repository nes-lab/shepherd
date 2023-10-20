# import sys
# print(sys.path)
# sys.path.append('/home/vishal/shepherd/software/firmware/pru0-cython-module')
# import pyximport
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig
from shepherd_core.vsource import VirtualConverterModel

vscfg = VirtualSourceConfig()
vccfg = ConverterPRUConfig.from_vsrc(data=vscfg)
vconv = VirtualConverterModel(cfg=vccfg.export_for_sysfs())

x = 0
print(vconv.calc_out_power(x))
print(vconv.calc_inp_power(5, 6))
