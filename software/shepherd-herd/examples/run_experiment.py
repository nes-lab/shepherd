"""
This describes a typical scripted workflow for running experiments on the Testbed.

Example assumes:
- access to herd-server
- inventory at /etc/shepherd/herd.yml
- passwordless access to sheep

"""

from pathlib import Path
from pathlib import PurePosixPath

from shepherd_core import TestbedClient
from shepherd_core.data_models import EnergyEnvironment
from shepherd_core.data_models import Experiment
from shepherd_core.data_models import Firmware
from shepherd_core.data_models import TargetConfig
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.task import TestbedTasks
from shepherd_herd import Herd

path_local = Path(__file__).parent
path_tasks = path_local / "experiment_tb_tasks.yaml"


# ######################################################
# PART 1: Defining an Experiment
# ######################################################
# mostly copied from core-lib/examples/firmware_model.py
# [xp-definition-start]

target_configs = [
    # first Instance similar to yaml-syntax
    TargetConfig(
        target_IDs=[3001, 3002, 3003],
        custom_IDs=[0, 1, 2],
        energy_env={"name": "SolarSunny"},
        virtual_source={"name": "diode+capacitor"},
        firmware1={"name": "nrf52_demo_rf"},
    ),
    # second Instance fully object-oriented (recommended)
    TargetConfig(
        target_IDs=list(range(2001, 2005)),
        custom_IDs=list(range(7, 18)),  # note: longer list is OK
        energy_env=EnergyEnvironment(name="ThermoelectricWashingMachine"),
        virtual_source=VirtualSourceConfig(name="direct"),
        firmware1=Firmware(name="nrf52_demo_rf"),
        firmware2=Firmware(name="msp430_deep_sleep"),
    ),
]

xp1 = Experiment(
    id="4567",
    name="meaningful Test-Name",
    time_start="2033-03-13 14:15:16",  # or: datetime.now() + timedelta(minutes=30)
    target_configs=target_configs,
    duration=10,
)

# [xp-definition-end]
# ######################################################
# PART 2: Generating a Task-Set
# ######################################################
# [tset-definition-start]

# TODO: this will definitely change in the near future or at least needs a login

tb_client = TestbedClient()
do_connect = False

if do_connect:
    tb_client.connect()

tb_tasks1 = TestbedTasks.from_xp(xp1)

tb_tasks1.to_file(path_tasks)

# [tset-definition-end]
# ######################################################
# PART 3: run the Task-set
# ######################################################
# alternative: use herd CLI
# [herd-run-start]

with Herd(inventory="/etc/shepherd/herd.yml") as herd:
    # NOTE: that's one of the default paths for the inventory
    #       and therefore not needed here

    variant1 = True

    if variant1:
        # more control
        remote_config = PurePosixPath("/etc/shepherd/config_task.yaml")
        herd.put_file(path_tasks, dst=remote_config, force_overwrite=True)
        command = f"shepherd-sheep --verbose run {remote_config.as_posix()}"
        replies = herd.run_cmd(sudo=True, cmd=command)
        herd.print_output(replies, verbose=True)
    else:
        herd.run_task(tb_tasks1, attach=True)

    # ######################################################
    # PART 4: Retrieving files
    # ######################################################
    # alternative: use herd CLI

    herd.get_task_files(tb_tasks1, dst_dir=path_local, delete_src=True)
    # NOTE1: sheep and herd-server both have access to the same nfs-drive
    # NOTE2: this routine is not finished

# [herd-run-end]
