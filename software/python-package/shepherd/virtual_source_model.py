"""

this is ported py-version of the pru-code, goals:
- stay close to original code-base
- offer a comparison for the tests
- step 1 to a virtualization of emulation

NOTE: DO NOT OPTIMIZE -> stay close to original code-base

"""
from typing import Optional

from shepherd_core import CalibrationEmulator

from .virtual_converter_model import KernelConverterStruct
from .virtual_converter_model import PruCalibration
from .virtual_converter_model import VirtualConverterModel
from .virtual_harvester_config import VirtualHarvesterConfig
from .virtual_harvester_model import KernelHarvesterStruct
from .virtual_harvester_model import VirtualHarvesterModel
from .virtual_source_config import T_vSrc
from .virtual_source_config import VirtualSourceConfig


class VirtualSourceModel:
    """part of sampling.c"""

    def __init__(
        self,
        vs_setting: Optional[T_vSrc],
        cal_emu: CalibrationEmulator,
        input_setting: Optional[dict],
    ):
        self._cal: CalibrationEmulator = cal_emu
        self._prc: PruCalibration = PruCalibration(cal_emu)

        vs_config = VirtualSourceConfig(vs_setting)
        vc_struct = KernelConverterStruct(vs_config)
        self.cnv: VirtualConverterModel = VirtualConverterModel(vc_struct, self._prc)

        vh_config = VirtualHarvesterConfig(
            vs_config.get_harvester(),
            vs_config.samplerate_sps,
            emu_cfg=input_setting,
        )

        vh_struct = KernelHarvesterStruct(vh_config)
        self.hrv: VirtualHarvesterModel = VirtualHarvesterModel(vh_struct)

        self.W_inp_fWs: float = 0.0
        self.W_out_fWs: float = 0.0

    def iterate_sampling(self, V_inp_uV: int = 0, I_inp_nA: int = 0, A_out_nA: int = 0):
        """
        TEST-SIMPLIFICATION - code below is not part of pru-code,
        but in part sample_emulator() in sampling.c

        :param V_inp_uV:
        :param I_inp_nA:
        :param A_out_nA:
        :return:
        """
        V_inp_uV, I_inp_nA = self.hrv.iv_sample(V_inp_uV, I_inp_nA)

        P_inp_fW = self.cnv.calc_inp_power(V_inp_uV, I_inp_nA)

        # fake ADC read
        A_out_raw = self._cal.adc_C_A.si_to_raw(A_out_nA * 10**-9)

        P_out_fW = self.cnv.calc_out_power(A_out_raw)
        self.cnv.update_cap_storage()
        V_out_raw = self.cnv.update_states_and_output()
        V_out_uV = int(self._cal.dac_V_A.raw_to_si(V_out_raw) * 10**6)

        self.W_inp_fWs += P_inp_fW
        self.W_out_fWs += P_out_fW

        return V_out_uV
