import ctypes as ct
from pathlib import Path
from unittest.mock import patch

from shepherd_core import logger
from shepherd_core.data_models.content.virtual_harvester import HarvesterPRUConfig


class HarvesterConfig(ct.Structure):
    _pack_ = 1
    _fields_ = [(_key, ct.c_uint32) for _key in HarvesterPRUConfig.model_fields]


def get_device() -> ct.CDLL:
    path = Path(__file__).parent / "virtual_xyz.so"
    fn_signatures = {
        "harvester_initialize": ([ct.POINTER(HarvesterConfig)], None),
        "sample_ivcurve_harvester": ([ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_uint32)], None),
    }
    pru = ct.CDLL(path.as_posix())
    for _fn, _sig in fn_signatures.items():
        pru[_fn].argtypes = _sig[0]
        pru[_fn].restype = _sig[1]
    return pru


@patch(target="shepherd_core.vsource.virtual_harvester_model.VirtualHarvesterModel")
class PruHarvesterModel:
    def __init__(self, cfg: HarvesterPRUConfig) -> None:
        self.hrv_cfg = HarvesterConfig(**cfg.model_dump())
        logger.info("This is the PRU-C-Code-Model.")
        logger.info(cfg.model_dump())
        self.pru = get_device()
        self.pru.harvester_initialize(ct.byref(self.hrv_cfg))

    def ivcurve_sample(self, _voltage_uV: int, _current_nA: int) -> tuple[int, int]:
        val_v = ct.c_uint32(_voltage_uV)
        val_c = ct.c_uint32(_current_nA)
        self.pru.sample_ivcurve_harvester(ct.byref(val_v), ct.byref(val_c))
        return (val_v.value, val_c.value)
