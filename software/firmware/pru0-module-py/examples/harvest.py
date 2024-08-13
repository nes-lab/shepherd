from pathlib import Path

from shepherd_core import logger
from shepherd_core.data_models import VirtualHarvesterConfig

from shp_pru import simulate_harvester
from shepherd_data import Reader


hrv_list = [
    "ivcurve",
    "cv10",
    "cv20",
    "mppt_voc",
    "mppt_bq_solar",
    "mppt_bq_thermoelectric",
    "mppt_po",
    "mppt_opt",
]

path_input = Path(__file__).parent / "hrv_ivcurve.h5"
results: dict = {}

# #####################################################################
# Harvest emulation from IVCurves #####################################
# #####################################################################

for hrv_name in hrv_list[1:]:
    path_output = path_input.with_name(path_input.stem + "_" + hrv_name + "_cim" + path_input.suffix)
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
