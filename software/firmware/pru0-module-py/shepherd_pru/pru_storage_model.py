"""This is ported py-version of the pru-code.

Goals:

- stay close to original code-base
- offer a comparison for the tests
- step 1 to a virtualization of emulation.

NOTE: DO NOT OPTIMIZE -> stay close to original code-base

"""

import ctypes as ct

from shepherd_core.data_models.content.virtual_storage_config import VirtualStorageConfig
from shepherd_core.data_models.content.virtual_storage_config import soc_t
from shepherd_core.data_models.content.virtual_storage_config_pru import StoragePRUConfig
from shepherd_core.data_models.content.virtual_storage_config_pru import TIMESTEP_s_DEFAULT

from ._virtual_pru import virtual_pru
from .data_types import StorageConfig


class PruStorageModel:
    """Interface for virtual_storage.c"""

    def __init__(
        self,
        cfg: VirtualStorageConfig | None,
        SoC_init: soc_t | None = None,
    ) -> None:
        # metadata for simulator
        self.cfg = cfg
        self.dt_s = TIMESTEP_s_DEFAULT
        # initialize C-Code
        cfg_pru = StoragePRUConfig.from_vstorage(cfg, TIMESTEP_s_DEFAULT, optimize_clamp=True)
        cfg_dict = cfg_pru.model_dump()
        cfg_dict["SoC_init_1_n30"] = (
            2**30 * SoC_init if SoC_init is not None else cfg_pru.SoC_init_1_n30
        )
        cfg_struct = StorageConfig(**cfg_dict)
        self.pru = virtual_pru
        self.pru.set_storage_config(ct.byref(cfg_struct))
        self.pru.storage_initialize()
        # Different time-steps possible - see core/VirtualStorageModel

    def step(self, I_charge_A: float) -> tuple[float, float, float, float]:
        """Slower outer step with step-size of simulation."""
        I_delta_nA_n4 = int(abs(2**4 * (1e9 * I_charge_A)))
        is_charging = I_charge_A >= 0
        V_cell_uV_n8 = self.pru.storage_update(I_delta_nA_n4, is_charging)
        # code below just for simulation
        V_OC = 1e-6 * self.pru.get_V_OC_uV
        V_cell = (1e-6 / 2**8) * V_cell_uV_n8
        SoC = (1.0 / 2**30) * self.pru.get_SoC_1_n30
        return V_OC, V_cell, SoC, SoC
