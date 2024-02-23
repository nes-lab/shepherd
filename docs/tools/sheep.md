# Shepherd-Sheep-Tool

`shepherd-sheep` is the command line utility for locally controlling a single shepherd observer.
Depending on your use-case you may not even need to directly interact with it. Use the `shepherd-herd` command line utility to orchestrate a group of shepherd observer remotely.

For using the tool, deploy the software as described in [](../user/getting_started.md).

## Command-Line Interface

The command-line Interface is as follows:

```{eval-rst}
.. click:: shepherd_herd.herd_cli:cli
   :prog: shepherd-sheep
   :nested: full
```

## High-Level API

The shepherd-sheep API offers high level access to shepherd's functionality and forms the base for the two command line utilities.
With the introduction of the [core-lib](https://pypi.org/project/shepherd-core/) the api was simplified and modernized with a model-based approach. The [pydantic](https://docs.pydantic.dev) data-models offer self-validating config-parameters with neutral defaults.

For lower-level access, have a look at the [](#hrv-api) and [](#emu-api) below. There is a third option called `debug-api`, used i.e. by the programmer. 
It will not be documented here. 
To learn about the functionality [the source](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/shepherd_emulator.py) should be consulted.

### Harvesting

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

The snippet is taken from the actual implementation in [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [HarvestTask](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/task/harvest.py)

### Emulating

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

The snippet is taken from the actual implementation in [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [EmulationTask](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/task/emulation.py). 

:::{note}
TODO: add user/task-config and relink both tasks above
:::

### Modify Firmware

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

The snippet is taken from the actual implementation in [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [FirmwareModTask](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/task/firmware_mod.py). 

### Program Target

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

The snippet is taken from the actual implementation in [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [ProgrammingTask](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/task/programming.py). 

### Example-Code

This snippet shows the harvester and emulator instantiated with custom config-models. It was used as a 10h stress-test to find a memory leak. 

```{literalinclude} ../../software/python-package/tests_manual/testbench_longrun.py
:language: python
```

Source: [./tests_manual/testbench_longrun.py](https://github.com/orgua/shepherd/blob/main/software/python-package/tests_manual/testbench_longrun.py)


(hrv-api)=
## Harvester-API

```{eval-rst}
.. autoclass:: shepherd_sheep.ShepherdHarvester
    :members:
    :inherited-members:
```

(emu-api)=
## Emulator-API

```{eval-rst}
.. autoclass:: shepherd_sheep.ShepherdEmulator
    :members:
    :inherited-members:
```

## Reference

- [core-lib](https://github.com/orgua/shepherd-datalib/tree/main/shepherd_core/shepherd_core/data_models/task) data-models for custom tasks
- [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) for high-level api routines
