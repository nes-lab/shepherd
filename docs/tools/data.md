# Shepherd-Data

```{include} ../../software/shepherd-datalib/shepherd_data/README.md
   :start-line: 2
   :end-line: 31
```

## Command-Line Interface

:::{note}
The tool has integrated help-functionality. For a full list of supported commands and options, run `shepherd-herd --help` and for more detail for each command `shepherd-herd [COMMAND] --help`.
:::

The command-line Interface is as follows:

```{eval-rst}
.. click:: shepherd_data.cli:cli
   :prog: shepherd-data
   :nested: full
```

## Unittests

To run the testbench, follow these steps:

1. Navigate your host-shell into the package-folder and
2. install dependencies
3. run the testbench (~ 30 tests):

```Shell
cd shepherd-datalib/shepherd-data
pip3 install .[tests]
pytest
```
