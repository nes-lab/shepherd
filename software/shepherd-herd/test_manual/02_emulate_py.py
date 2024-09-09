from itertools import product
from pathlib import Path

from shepherd_core import logger
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.vsource import ResistiveTarget
from shepherd_core.vsource import simulate_source
from shepherd_data import Reader

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

host_selected = "sheep0"
path_here = Path(__file__).parent
results: dict = {}
target = ResistiveTarget(R_Ohm=1000)

# #####################################################################
# Emulate - simulated          ########################################
# #####################################################################

for hrv_name, src_name in product(hrv_list, src_list):
    path_input = path_here / host_selected / f"hrv_{hrv_name}.h5"
    path_output = path_input.with_name(
        path_input.stem + "_" + src_name + "_sim" + path_input.suffix
    )
    if not path_output.exists():
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
