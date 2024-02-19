# API

The shepherd API offers high level access to shepherd's functionality and forms the base for the two command line utilities.
With the introduction of the [core-lib](https://pypi.org/project/shepherd-core/) the api was simplified and modernized with a model-based approach. The [pydantic](https://docs.pydantic.dev) data-models offer self-validating config-parameters with neutral defaults.
Note that the API only converts local functionality on a single shepherd node.
Use the `shepherd-herd` command line utility to orchestrate a group of shepherd nodes remotely.

## Harvester

The recorder is used to configure all relevant hardware and software and to sample and extract data from the analog frontend.

```{eval-rst}
.. autoclass:: shepherd_sheep.ShepherdHarvester
    :members:
    :inherited-members:
```

Usage with a high-level example:

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

The example is taken from [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [HarvestTask](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/task/harvest.py)


## Emulator

The emulator is used to emulate previously recorded IV data to an attached sensor node.

```{eval-rst}
.. autoclass:: shepherd_sheep.ShepherdEmulator
    :members:
    :inherited-members:
```

Usage with a high-level example, task:

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

The example is taken from production code in [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) and references the [EmulationTask](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/task/emulation.py)

## Complete Example

This code shows the harvester and emulator instantiated with custom config-models. It was used as a 10h stress-test to find a memory leak.

:::{literalinclude} ../../software/python-package/tests_manual/testbench_longrun.py
:language: python
:::


## Programmer

### Modify Firmware

```{literalinclude} ../../software/python-package/shepherd_sheep/__init__.py
:language: python
:pyobject: run_firmware_mod
```

### Program Target

```{literalinclude} ../../software/python-package/shepherd_sheep/__init__.py
:language: python
:pyobject: run_programmer
```

## Reference

- [core-lib](https://github.com/orgua/shepherd-datalib/tree/main/shepherd_core/shepherd_core/data_models/task) data-models for custom tasks
- [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) for high-level api routines
