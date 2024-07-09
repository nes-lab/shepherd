# Shepherd-Herd

[![PyPiVersion](https://img.shields.io/pypi/v/shepherd_herd.svg)](https://pypi.org/project/shepherd_herd)
[![CodeStyle](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Main Documentation**: <https://orgua.github.io/shepherd/tools/herd>

**Main Project**: <https://github.com/orgua/shepherd>

**Source Code**: <https://github.com/orgua/shepherd/tree/main/software/shepherd_herd>

---

`Shepherd-herd` is the command line utility for controlling a group of shepherd observers remotely through an IP-based network.
This is the key user interface for a private shepherd instance in the same network.
The python package must be installed on the user's local machine and sends commands to the sheep via *ssh*.

## Installation

`shepherd-herd` is a python package and available on [PyPI](https://pypi.org/project/shepherd_herd).
Use your python package manager to install it.
For example, using pip:

```Shell
pip3 install shepherd-herd
```

For install directly from GitHub-Sources (here `dev`-branch):

```Shell
pip install git+https://github.com/orgua/shepherd.git@dev#subdirectory=software/shepherd-herd -U
```

For install from local sources:

```Shell
cd shepherd/software/shepherd-herd/
pip3 install . -U
```

## Usage

For details either use the help provided by the tool or have a look into the [documentation](https://orgua.github.io/shepherd/tools/herd)

## Library-Examples

See [example-files](https://github.com/orgua/shepherd/tree/main/software/shepherd-herd/examples/) for details.
