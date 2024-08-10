import ctypes as ct
from pathlib import Path
from typing import Tuple

from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig


class HarvesterConfig(ct.Structure):
    _pack_ = 1
    _fields_ = [(_key, ct.c_uint32) for _key in HarvesterPRUConfig.model_fields.keys()]


path = Path(__file__).parent / "virtual_xyz.so"
pru = ct.CDLL(path.as_posix())

pru.harvester_initialize.argtypes = [ct.POINTER(HarvesterConfig)]
pru.harvester_initialize.restype = None

pru.sample_ivcurve_harvester.argtypes = [ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_uint32)]
pru.sample_ivcurve_harvester.restype = None

class VirtualHarvesterModel:

    def __init__(self, cfg: HarvesterPRUConfig) -> None:
        self.hrv_cfg = HarvesterConfig(**cfg.model_dump())
        print(cfg.model_dump())
        pru.harvester_initialize(ct.byref(self.hrv_cfg))

    def ivcurve_sample(self, _voltage_uV: int, _current_nA: int) -> Tuple[int, int]:
        val_v = ct.c_uint32(_voltage_uV)
        val_c = ct.c_uint32(_current_nA)
        pru.sample_ivcurve_harvester(ct.byref(val_v), ct.byref(val_c))
        return (val_v.value, val_c.value)