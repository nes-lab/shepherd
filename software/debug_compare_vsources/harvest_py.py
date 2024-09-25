from pathlib import Path

from config import host_selected
from config import hrv_list
from shepherd_core import logger
from shepherd_core.data_models import VirtualHarvesterConfig
from shepherd_core.vsource import simulate_harvester
from shepherd_data import Reader

path_here = Path(__file__).parent
results: dict = {}

# #####################################################################
# Harvest emulation from IVCurves #####################################
# #####################################################################

path_input = path_here / host_selected / "hrv_ivcurve.h5"

for hrv_name in hrv_list[1:]:
    path_output = path_input.with_name(
        path_input.stem + "_" + hrv_name + "_py_sim" + path_input.suffix
    )
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
