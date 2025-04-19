from pathlib import Path

from shepherd_core import logger
from shepherd_core.data_models import VirtualHarvesterConfig
from shepherd_data import Reader
from shepherd_pru import simulate_harvester

from .config import host_selected
from .config import hrv_list

path_input = Path(__file__).parent / host_selected / "hrv_ivcurve.h5"
results: dict = {}

# #####################################################################
# Harvest emulation from IVCurves #####################################
# #####################################################################

for hrv_name in hrv_list[1:]:
    path_output = path_input.with_stem(path_input.stem + "_" + hrv_name + "_cpy_sim")
    if not path_output.exists():
        simulate_harvester(
            config=VirtualHarvesterConfig(name=hrv_name),
            path_input=path_input,
            path_output=path_output,
        )
    with Reader(path_output) as _fh:
        results[path_output.stem] = _fh.energy()

logger.info("Finished with:")
for _key, _value in results.items():
    logger.info("\t%s = %.6f mWs", _key, 1e3 * _value)
