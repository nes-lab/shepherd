import ctypes as ct

from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig
from shepherd_core.logger import log

from ._virtual_pru import virtual_pru
from .data_types import HarvesterConfig


# @patch(target="shepherd_core.vsource.virtual_harvester_model.VirtualHarvesterModel")
class PruHarvesterModel:
    def __init__(self, cfg: HarvesterPRUConfig) -> None:
        self.hrv_cfg = HarvesterConfig(**cfg.model_dump())
        log.info("This is the PRU-C-HRV-Model.")
        log.info(cfg.model_dump())
        self.pru = virtual_pru
        self.pru.harvester_initialize(ct.byref(self.hrv_cfg))

    def ivcurve_sample(self, _voltage_uV: int, _current_nA: int) -> tuple[int, int]:
        val_v = ct.c_uint32(_voltage_uV)
        val_c = ct.c_uint32(_current_nA)
        self.pru.sample_ivcurve_harvester(ct.byref(val_v), ct.byref(val_c))
        return (val_v.value, val_c.value)
