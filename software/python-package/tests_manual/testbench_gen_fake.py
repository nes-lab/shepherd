# playground for failing unit-tests
from pathlib import Path

import numpy as np
from shepherd_core.data_models.base.calibration import CalibrationHarvester
from shepherd_core.writer import Writer
from shepherd_sheep.commons import SAMPLE_INTERVAL_NS

tmp_path = Path("/var/shepherd/recordings")
store_path = tmp_path / "harvest_example.h5"


def random_data(length: int) -> np.ndarray:
    rng = np.random.default_rng()
    return rng.integers(low=0, high=2**18, size=length, dtype=np.uint32)


with Writer(store_path, cal_data=CalibrationHarvester()) as store:
    store.store_hostname("Blinky")
    len_ = 10_000
    for i in range(100):
        store.append_iv_data_raw(
            timestamp=i * len_ * SAMPLE_INTERVAL_NS,
            voltage=random_data(len_),
            current=random_data(len_),
        )

# run with
# sudo shepherd-sheep -v emulator -d 10 --force_overwrite
#   --virtsource /opt/shepherd/software/python-package/tests/_test_config_virtsource.yaml
#   -o /var/shepherd/recordings/out.h5 /var/shepherd/recordings/harvest_example.h5
# echo $?
