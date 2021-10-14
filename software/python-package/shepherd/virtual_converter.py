from typing import NoReturn
from shepherd import VirtualConverterData, CalibrationData
import math

# NOTE: DO NOT OPTIMIZE -> stay close to original code-base


class VirtualConverter(object):
    """
    this is ported py-version of the pru-code, goals:
    - stay close to original code-base
    - offer a comparison for the tests
    - step 1 to a virtualization of emulation

    """

    def __init__(self, vd_setting, cal_setting):

        if cal_setting is not None:
            self.cal = cal_setting

        # NOTE:
        #  - yaml is based on si-units like nA, mV, ms, uF
        #  - c-code and py-copy is using nA, uV, ns, nF, fW
        vd_setting = VirtualConverterData(vd_setting)
        values = vd_setting.export_for_sysfs()

    def ivcurves_to_params(self, v: float, c: float):
        # static:
        age_new = age_old = p_max_new = p_max_old = 0
        window_size = 250

        p_atm = v * c
        age_new += 1
        age_old += 1
        if p_atm > p_max_new:
            p_max_new = p_atm
            age_new = 0
        if (age_old > window_size) or (p_max_new >= p_max_old):
            p_max_old = p_max_new
            age_old = age_new
            p_max_new = 0
            age_new = 0
        return p_max_old

    def mppt_voc(self):
        print("test")
