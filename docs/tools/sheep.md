# Shepherd-Sheep

`shepherd-sheep` is the command line utility for locally controlling a single shepherd observer.
Depending on your use-case you may not even need to directly interact with it. Use the `shepherd-herd` command line utility to orchestrate a group of shepherd observer remotely.

For using the tool, deploy the software as described in [](../user/getting_started.md).

## Command-Line Interface

:::{note}
The tool has integrated help-functionality. For a full list of supported commands and options, run `shepherd-sheep --help` and for more detail for each command `shepherd-sheep [COMMAND] --help`.
:::

The command-line Interface is as follows:

```{eval-rst}
.. click:: shepherd_herd.herd_cli:cli
   :prog: shepherd-sheep
   :nested: full
```

## Unittests

To run the full range of python tests, have a copy of the source code on a BeagleBone.
Build and install from source (see [](../user/getting_started) for more).
Change into the `software/python-package` directory on the BeagleBone and run the following commands to:

- install dependencies of tests
- run testbench

```shell
cd /opt/shepherd/software/python-package
sudo pip3 install ./[tests]
sudo pytest-3
```

Some tests (~40) are hardware-independent, while most of them require a BeagleBone to work (~100). The testbench detects the BeagleBone automatically. A small subset of tests (~8) are writing & configuring the EEPROM on the shepherd cape and must be enabled manually (`sudo pytest --eeprom-write`)

The following commands allow to:

- restartable run that exits for each error (perfect for debugging on slow BBone)
- run single tests,
- whole test-files or

```shell
sudo pytest-3 --stepwise

sudo pytest-3 tests/test_sheep_cli.py::test_cli_emulate_aux_voltage

sudo pytest-3 tests/test_sheep_cli.py
```

## Reference

- [core-lib](https://github.com/orgua/shepherd-datalib/tree/main/shepherd_core/shepherd_core/data_models/task) data-models for custom tasks
- [sheep/init](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/__init__.py) for high-level api routines
