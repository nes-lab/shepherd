from itertools import product
from pathlib import Path

from shepherd_core import logger
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.vsource import ResistiveTarget
from shepherd_data import Reader
from shepherd_pru.pru_source_simulation import simulate_source

hrv_list = [
    "ivcurve",
    "mppt_voc",
    "mppt_po",
]

src_list = [
    "direct",
    "dio_cap",
    "BQ25504",
    "BQ25570",
]

target = ResistiveTarget(resistance_Ohm=1000)

paths_local_hrv = {hrv_name: Path(__file__).parent / f"hrv_{hrv_name}.h5" for hrv_name in hrv_list}
results: dict = {}

# #####################################################################
# Emulate - simulated          ########################################
# #####################################################################

for hrv_name, src_name in product(hrv_list, src_list):
    path_input = paths_local_hrv[hrv_name]
    path_output = path_input.with_name(
        path_input.stem + "_" + src_name + "_cim" + path_input.suffix
    )
    # if not path_output.exists():
    simulate_source(
        config=VirtualSourceConfig(
            inherit_from=src_name,
            C_output_uF=0,
        ),
        target=target,
        path_input=path_input,
        path_output=path_output,
    )
    with Reader(path_output, verbose=False) as _fh:
        results[path_output.stem] = _fh.energy()

logger.info("Finished with:")
for _key, _value in results.items():
    logger.info("\t%s = %.6f mWs", _key, 1e3 * _value)
