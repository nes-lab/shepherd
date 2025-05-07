from itertools import product
from pathlib import Path

from config import emu_hrv_list
from config import emu_src_list
from config import emu_target
from config import host_selected
from shepherd_core import logger
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_data import Reader
from shepherd_pru.pru_source_simulation import simulate_source

path_here = Path(__file__).parent
results: dict = {}

# #####################################################################
# Emulate - simulated          ########################################
# #####################################################################

for hrv_name, src_name in product(emu_hrv_list, emu_src_list):
    path_input = Path(__file__).parent / host_selected / f"hrv_{hrv_name}.h5"
    path_output = path_input.with_stem(path_input.stem + "_" + src_name + "_cpy_sim")
    if not path_output.exists():
        simulate_source(
            config=VirtualSourceConfig(
                inherit_from=src_name,
                C_output_uF=0,
            ),
            target=emu_target,
            path_input=path_input,
            path_output=path_output,
        )
    with Reader(path_output, verbose=False) as _fh:
        results[path_output.stem] = _fh.energy()

logger.info("Finished with:")
for _key, _value in results.items():
    logger.info("\t%s = %.6f mWs", _key, 1e3 * _value)
