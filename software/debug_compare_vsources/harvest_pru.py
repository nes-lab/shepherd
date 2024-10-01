from contextlib import ExitStack
from pathlib import Path

from config import host_selected
from config import hrv_list
from shepherd_core import logger
from shepherd_core.data_models import VirtualHarvesterConfig
from shepherd_core.data_models.task import HarvestTask
from shepherd_data import Reader
from shepherd_herd import Herd

path_here = Path(__file__).parent
results: dict = {}

# #####################################################################
# Harvest from real transducer ########################################
# #####################################################################

for hrv_name in hrv_list:
    file_name = f"hrv_{hrv_name}.h5"
    path_remote = Path("/tmp/" + file_name)  # noqa: S108
    path_local = path_here / host_selected / file_name

    if not path_local.exists():
        logger.info("Start harvesting with '%s'", hrv_name)
        stack = ExitStack()
        herd = Herd(inventory="/etc/shepherd/herd.yml", limit=host_selected)
        stack.enter_context(herd)
        task = HarvestTask(
            duration=30,
            output_path=path_remote,
            virtual_harvester=VirtualHarvesterConfig(name=hrv_name),
            use_cal_default=True,
            force_overwrite=True,
        )
        if herd.run_task(task, attach=True) == 0:
            # note: herd will add host-name to path
            herd.get_file(path_remote, path_here, separate=True, delete_src=True)
        else:
            logger.error("Failed to harvest with '%s'", hrv_name)
        stack.close()

    with Reader(path_local) as _fh:
        results[path_local.stem] = _fh.energy()

logger.info("Finished with:")
for _key, _value in results.items():
    logger.info("\t%s = %.6f mWs", _key, 1e3 * _value)
