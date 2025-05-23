# Shepherd-Sheep

The shepherd-sheep API offers high level access to shepherd's functionality and forms the base for the two command line utilities.
With the introduction of the [core-lib](https://pypi.org/project/shepherd-core/) the api was simplified and modernized with a model-based approach. The [pydantic](https://docs.pydantic.dev) data-models offer self-validating config-parameters with neutral defaults.

For lower-level access, have a look at the [](sheep_low_level.md). There is a third option called `debug-api`, used i.e. by the programmer.
It will not be documented here.
To learn about the functionality [the source](https://github.com/nes-lab/shepherd/blob/main/software/python-package/shepherd_sheep/shepherd_emulator.py) should be consulted.

## Harvesting

The `run_harvester()`-function can be used to configure all relevant hardware and software and to sample and extract data from the analog frontend.

```python
from contextlib import ExitStack

from shepherd_core.data_models.task import HarvestTask
from shepherd_sheep.shepherd_harvester import ShepherdHarvester
from shepherd_sheep.logger import set_verbosity
```
```{literalinclude} ../../software/python-package/shepherd_sheep/__init__.py
:language: python
:pyobject: run_harvester
```

The snippet is taken from the actual implementation in [sheep/init](https://github.com/nes-lab/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [HarvestTask](https://github.com/nes-lab/shepherd-tools/blob/main/shepherd_core/shepherd_core/data_models/task/harvest.py)

## Emulating

The `run_emulator()`-function can be used to emulate previously recorded IV data for an attached sensor node.

```python
from contextlib import ExitStack

from shepherd_core.data_models.task import EmulationTask
from shepherd_sheep.shepherd_emulator import ShepherdEmulator
from shepherd_sheep.logger import set_verbosity
```
```{literalinclude} ../../software/python-package/shepherd_sheep/__init__.py
:language: python
:pyobject: run_emulator
```

The snippet is taken from the actual implementation in [sheep/init](https://github.com/nes-lab/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [EmulationTask](https://github.com/nes-lab/shepherd-tools/blob/main/shepherd_core/shepherd_core/data_models/task/emulation.py).

:::{note}
TODO: add user/task-config and relink both tasks above
:::

## Modify Firmware

The `run_firmware_mod()`-function can be used to customize a firmware before flashing it.

```python
import shutil

from shepherd_core.data_models import FirmwareDType
from shepherd_core.data_models.task import FirmwareModTask
from shepherd_core.fw_tools import extract_firmware
from shepherd_core.fw_tools import firmware_to_hex
from shepherd_core.fw_tools import modify_uid
from shepherd_sheep.logger import set_verbosity
from shepherd_sheep.sysfs_interface import check_sys_access
```
```{literalinclude} ../../software/python-package/shepherd_sheep/__init__.py
:language: python
:pyobject: run_firmware_mod
```

The snippet is taken from the actual implementation in [sheep/init](https://github.com/nes-lab/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [FirmwareModTask](https://github.com/nes-lab/shepherd-tools/blob/main/shepherd_core/shepherd_core/data_models/task/firmware_mod.py).

## Program Target

The `run_programmer()`-function can flash a `.hex`-file to a target of choice.

```python
from contextlib import ExitStack

from shepherd_core.data_models.task import ProgrammingTask
from shepherd_sheep import sysfs_interface
from shepherd_sheep.logger import set_verbosity
from shepherd_sheep.shepherd_debug import ShepherdDebug
# Note: probably some includes missing
```
```{literalinclude} ../../software/python-package/shepherd_sheep/__init__.py
:language: python
:pyobject: run_programmer
```

The snippet is taken from the actual implementation in [sheep/init](https://github.com/nes-lab/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [ProgrammingTask](https://github.com/nes-lab/shepherd-tools/blob/main/shepherd_core/shepherd_core/data_models/task/programming.py).

## Example-Code

This snippet shows the harvester and emulator instantiated with custom config-models. It was used as a 10h stress-test to find a memory leak.

```{literalinclude} ../../software/python-package/tests_manual/testbench_longrun.py
:language: python
```

Source: [./tests_manual/testbench_longrun.py](https://github.com/nes-lab/shepherd/blob/main/software/python-package/tests_manual/testbench_longrun.py)
