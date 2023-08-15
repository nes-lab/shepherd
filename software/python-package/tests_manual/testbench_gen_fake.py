# playground for failing unit-tests
from pathlib import Path

import numpy as np
from shepherd_core import CalibrationHarvester
from shepherd_sheep import Writer
from shepherd_sheep.shared_memory import DataBuffer

tmp_path = Path("/var/shepherd/recordings")
store_path = tmp_path / "harvest_example.h5"


def random_data(length):
    return np.random.randint(0, high=2**18, size=length, dtype="u4")


with Writer(store_path, cal_data=CalibrationHarvester()) as store:
    store.store_hostname("Blinky")
    for i in range(100):
        len_ = 10_000
        fake_data = DataBuffer(random_data(len_), random_data(len_), i)
        store.write_buffer(fake_data)

# run with
# sudo shepherd-sheep -vvv emulator -d 10 --force_overwrite
#   --virtsource /opt/shepherd/software/python-package/tests/_test_config_virtsource.yaml
#   -o /var/shepherd/recordings/out.h5 /var/shepherd/recordings/harvest_example.h5
# echo $?
