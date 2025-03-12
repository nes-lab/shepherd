from contextlib import ExitStack
from itertools import product
from pathlib import Path, PurePosixPath

from config import emu_hrv_list
from config import emu_src_list
from config import host_selected
from shepherd_core import logger
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.task import EmulationTask
from shepherd_data import Reader
from shepherd_herd import Herd

path_here = Path(__file__).parent
results: dict = {}

# #####################################################################
# Transfer Files to Observer   ########################################
# #####################################################################

paths_local_hrv = {}
paths_remote_hrv = {}
with Herd(inventory="/etc/shepherd/herd.yml", limit=host_selected) as herd:
    for hrv_name in emu_hrv_list:
        file_name = f"hrv_{hrv_name}.h5"
        paths_local_hrv[hrv_name] = path_here / host_selected / file_name
        paths_remote_hrv[hrv_name] = PurePosixPath("/tmp/" + file_name)  # noqa: S108
        logger.info("Start transferring '%s'", file_name)
        herd.put_file(paths_local_hrv[hrv_name], paths_remote_hrv[hrv_name], force_overwrite=True)

# #####################################################################
# Emulate with real Target     ########################################
# #####################################################################

for hrv_name, src_name in product(emu_hrv_list, emu_src_list):
    path_remote_hrv = paths_remote_hrv[hrv_name]
    path_remote_src = path_remote_hrv.with_name(
        path_remote_hrv.stem + "_" + src_name + "_pru_emu" + path_remote_hrv.suffix
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
            logger.error("Failed to emulate with '%s'", hrv_name)
        stack.close()

    with Reader(path_local_src) as _fh:
        results[path_local_src.stem] = _fh.energy()

logger.info("Finished with:")
for _key, _value in results.items():
    logger.info("\t%s = %.6f mWs", _key, 1e3 * _value)
