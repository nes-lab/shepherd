from contextlib import ExitStack
from itertools import product
from pathlib import Path

import numpy as np
from shepherd_core import CalibrationEmulator
from shepherd_core import Writer
from shepherd_core import logger
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.vsource import VirtualSourceModel, simulate_source, ResistiveTarget
from shepherd_data import Reader
from shepherd_herd import Herd
from tqdm import tqdm

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
target = ResistiveTarget(resistance_Ohm=1000)

# #####################################################################
# Transfer Files to Observer   ########################################
# #####################################################################

paths_local_hrv = {}
paths_remote_hrv = {}
with Herd(inventory="/etc/shepherd/herd.yml", limit=host_selected) as herd:
    for hrv_name in hrv_list:
        file_name = f"hrv_{hrv_name}.h5"
        paths_local_hrv[hrv_name] = path_here / host_selected / file_name
        paths_remote_hrv[hrv_name] = Path("/tmp/" + file_name)
        logger.info("Start transferring '%s'", file_name)
        herd.put_file(paths_local_hrv[hrv_name], paths_remote_hrv[hrv_name], force_overwrite=True)

# #####################################################################
# Emulate with real Target     ########################################
# #####################################################################

for hrv_name, src_name in product(hrv_list, src_list):
    path_remote_hrv = paths_remote_hrv[hrv_name]
    path_remote_src = path_remote_hrv.with_name(
        path_remote_hrv.stem + "_" + src_name + "_emu" + path_remote_hrv.suffix
    )
    path_local_src = path_here / host_selected / path_remote_src.name

    if not path_local_src.exists():
        stack = ExitStack()
        herd = Herd(inventory="/etc/shepherd/herd.yml", limit=host_selected)
        stack.enter_context(herd)
        task = EmulationTask(
            input_path=path_remote_hrv,
            output_path=path_remote_src,
            virtual_source=VirtualSourceConfig(inherit_from=src_name, C_output_uF=0),
            force_overwrite=True,
        )
        if herd.run_task(task, attach=True) == 0:
            herd.get_file(path_remote_src, path_here, separate=True, delete_src=True)
        else:
            logger.error("Failed to harvest with '%s'", hrv_name)
        stack.close()

    with Reader(path_local_src) as _fh:
        results[path_local_src.stem] = _fh.energy()

# #####################################################################
# Emulate - simulated          ########################################
# #####################################################################

for hrv_name, src_name in product(hrv_list, src_list):
    path_input = paths_local_hrv[hrv_name]
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
