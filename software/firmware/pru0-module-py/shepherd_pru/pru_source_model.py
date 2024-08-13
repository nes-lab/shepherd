"""This is ported py-version of the pru-code.

Goals:

- stay close to original code-base
- offer a comparison for the tests
- step 1 to a virtualization of emulation.

NOTE: DO NOT OPTIMIZE -> stay close to original code-base

"""

from shepherd_core.data_models import CalibrationEmulator
from shepherd_core.data_models import EnergyDType
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.data_models.content.virtual_source import ConverterPRUConfig

from .pru_converter_model import PruCalibration
from .pru_converter_model import PruConverterModel as VirtualConverterModel
from .pru_harvester_model import PruHarvesterModel as VirtualHarvesterModel


class PruSourceModel:
    """part of sampling.c."""

    def __init__(
        self,
        vsrc: VirtualSourceConfig | None,
        cal_emu: CalibrationEmulator,
        dtype_in: EnergyDType = EnergyDType.ivsample,
        window_size: int | None = None,
        *,
        log_intermediate: bool = False,
    ) -> None:
        self._cal_emu: CalibrationEmulator = cal_emu
        self._cal_pru: PruCalibration = PruCalibration(cal_emu)

        self.cfg_src = VirtualSourceConfig() if vsrc is None else vsrc
        cnv_config = ConverterPRUConfig.from_vsrc(
            self.cfg_src, log_intermediate_node=log_intermediate
        )
        self.cnv: VirtualConverterModel = VirtualConverterModel(cnv_config, self._cal_pru)

        hrv_config = HarvesterPRUConfig.from_vhrv(
            self.cfg_src.harvester,
            for_emu=True,
            dtype_in=dtype_in,
            window_size=window_size,
        )

        self.hrv: VirtualHarvesterModel = VirtualHarvesterModel(hrv_config)

        self.W_inp_fWs: float = 0.0
        self.W_out_fWs: float = 0.0

    def iterate_sampling(self, V_inp_uV: int = 0, I_inp_nA: int = 0, I_out_nA: int = 0) -> int:
        """TEST-SIMPLIFICATION - code below is not part of pru-code.

        It originates from sample_emulator() in sampling.c.

        :param V_inp_uV:
        :param I_inp_nA:
        :param I_out_nA:
        :return:
        """
        I_out_raw = self._cal_emu.adc_C_A.si_to_raw(1e-9 * I_out_nA)
        V_out_uV = self.cnv.vsrc_iterate_sampling(V_inp_uV, I_inp_nA, int(I_out_raw))
        P_inp_fW = self.cnv.get_P_input_fW()
        P_out_fW = self.cnv.get_P_output_fW()
        V_mid_uV = self.cnv.get_V_intermediate_uV()
        self.W_inp_fWs += P_inp_fW
        self.W_out_fWs += P_out_fW

        return V_mid_uV if self.cnv.get_state_log_intermediate() else V_out_uV
