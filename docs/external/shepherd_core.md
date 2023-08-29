# Core Library

[![PyPiVersion](https://img.shields.io/pypi/v/shepherd_core.svg)](https://pypi.org/project/shepherd_core)
[![Pytest](https://github.com/orgua/shepherd-datalib/actions/workflows/python-app.yml/badge.svg)](https://github.com/orgua/shepherd-datalib/actions/workflows/python-app.yml)
[![CodeStyle](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Documentation**: <https://orgua.github.io/shepherd/external/shepherd_core.html>

**Source Code**: <https://github.com/orgua/shepherd-datalib>

**Main Project**: <https://github.com/orgua/shepherd>

---

This Python Module is designed as a library and bundles data-models and file-access-routines for the shepherd-testbed, that are used by several codebases.

For postprocessing shepherds .h5-files users want to use [shepherd_data](https://pypi.org/project/shepherd_data).

## Features

- read and write shepherds hdf5-files
- create, read, write and convert experiments for the testbed (all data-models included)
- simulate the virtual source, including virtual harvesters (and virtual converter as a whole)
- connect and query the testbed via a webclient (TestbedClient)
  - offline usage defaults to static demo-fixtures loaded from yaml-files in the model-directories
- work with target-firmwares
  - embed, modify, verify, convert
  - **Note**: working with ELF-files requires external dependencies, see ``Installation``-Chapter
- decode waveforms (gpio-state & timestamp) to UART
- create an inventory (used versions of software, hardware)

See [examples](https://github.com/orgua/shepherd-datalib/tree/main/shepherd_core/examples) for more details and usage. Most functionality is showcased there. The [extra](https://github.com/orgua/shepherd-datalib/tree/main/shepherd_core/extra)-directory holds data-generators relevant for the testbed. Notably is a trafficbench-experiment that's used to derive the link-matrix.

### Data-Models in Detail

- new orchestration ``/data-models`` with focus on remote shepherd-testbed
- classes of sub-models
  - ``/base``: base-classes, configuration and -functionality for all models
  - ``/testbed``: meta-data representation of all testbed-components
  - ``/content``: reusable meta-data for fw, h5 and vsrc-definitions
  - ``/experiment``: configuration-models including sub-systems
  - ``/task``: digestible configs for shepherd-herd or -sheep
  - behavior controlled by ``ShpModel`` and ``content``-model
- a basic database is available as fixtures through a ``tb_client``
  - fixtures selectable by name & ID
  - fixtures support inheritance
- models support
  - auto-completion with neutral / sensible values
  - complex and custom datatypes (i.e. PositiveInt, lists-checks on length)
  - checking of inputs and type-casting
  - generate their own schema (for web-forms)
  - pre-validation
  - store to & load from yaml with typecheck through wrapper
  - documentation
- experiment-definition is designed securely
  - types are limited in size (str)
  - exposes no internal paths
- experiments can be transformed to task-sets (``TestbedTasks.from_xp()``)

## Installation

The Library is available via PyPI and can be installed with

```shell
  pip install shepherd-core -U

  # or for the full experience (includes core)
  pip install shepherd-data -U
```

For bleeding-edge-features or dev-work it is possible to install directly from GitHub-Sources (here `dev`-branch):

```Shell
pip install git+https://github.com/orgua/shepherd-datalib.git@dev#subdirectory=shepherd_core -U
```

If you are working with ``.elf``-files (embedding into experiments) you make "objcopy" accessible to python. In Ubuntu, you can either install ``build-essential`` or ``binutils-$ARCH`` with arch being ``msp430`` or ``arm-none-eabi`` for the nRF52.

```shell
  sudo apt install build-essential
```

For more advanced work with ``.elf``-files (modify value of symbols / target-ID) you should install

```shell
  pip install shepherd-core[elf]
```

and also make sure the prereqs for the [pwntools](https://docs.pwntools.com/en/stable/install.html) are met.

For creating an inventory of the host-system you should install

```shell
  pip install shepherd-core[inventory]
```

## Development

### PipEnv

- clone repository
- navigate shell into directory
- install environment
- activate shell
- optional
  - update pipenv (optional)
  - add special packages with `-dev` switch

```Shell
git clone https://github.com/orgua/shepherd-datalib
cd .\shepherd-datalib

pipenv install --dev
pipenv shell

pipenv update
pipenv install --dev pytest
```

### running Testbench

- run pytest in ``_core``- or ``_data``-subdirectory
- alternative

```shell
pytest
pytest --stepwise
```

### code coverage (with pytest)

- run coverage in ``_core``- or ``_data``-subdirectory
- check results (in browser `./htmlcov/index.html`)

```shell
coverage run -m pytest

coverage html
# or simpler
coverage report
```
