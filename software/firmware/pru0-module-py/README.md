# SHEPHERD-PRU Python-Module

This directory contains a python-interface to access virtual-source and -harvesting routines written in `c` for the pru.
The source-files are directly used by compiling them into a shared-object and accessing them via ctypes-wrappers.

## Setup

The workflow was only tested on Linux with GCC and Python installed.

```Shell
# if not already
cd pru0-module-py

# create the shared object
make

# install shepherd-pru python-module
pip install . -U
```
