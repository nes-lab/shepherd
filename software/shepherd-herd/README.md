# Shepherd-Herd

[![PyPiVersion](https://img.shields.io/pypi/v/shepherd_herd.svg)](https://pypi.org/project/shepherd_herd)
[![CodeStyle](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

*Shepherd-herd* is the command line utility for controlling a group of shepherd nodes remotely through an IP-based network.

---

**Documentation**: [https://orgua.github.io/shepherd/](https://orgua.github.io/shepherd/)

**Source Code**: [https://github.com/orgua/shepherd](https://github.com/orgua/shepherd)

---

## Installation

*shepherd-herd* is a python package and available on [PyPI](https://pypi.org/project/shepherd_herd).
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

All *shepherd-herd* commands require the list of hosts on which to perform the requested action.
This list of hosts is provided with the `-i` option, that takes either the path to a file or a comma-separated list of hosts (compare Ansible `-i`).

For example, save the following file in your current working directory as an ansible style, YAML-formatted inventory file named `herd.yml`.

```yaml
sheep:
  hosts:
    sheep0:
    sheep1:
    sheep2:
  vars:
    ansible_user: jane
```

To find active nodes a ping-sweep (in this example from .1 to .64) can be achieved with:

```Shell
nmap -sn 192.168.1.1-64
```

After setting up the inventory, use shepherd-herd to check if all your nodes are responding correctly:

```Shell
shepherd-herd -i herd.yml shell-cmd "echo 'hello'"
```

Or, equivalently define the list of hosts on the command line

```Shell
shepherd-herd -i sheep0,sheep1,sheep2, shell-cmd "echo 'hello'"
```

To **simplify usage** it is recommended to set up the `herd.yml` in either of these directories (with falling lookup priority):

- relative to your current working directory in `inventory/herd.yml`
- in your local home-directory `~/herd.yml`
- in the **config path** `/etc/shepherd/herd.yml` (**recommendation**)

From then on you can just call:

```Shell
shepherd-herd shell-cmd "echo 'hello'"
```

Or select individual sheep from the herd:

```Shell
shepherd-herd --limit sheep0,sheep2, shell-cmd "echo 'hello'"
```

## Library-Examples

See [example-files](https://github.com/orgua/shepherd/tree/main/software/shepherd-herd/examples/) for details.


## CLI-Examples

Here, we just provide a selected set of examples of how to use *shepherd-herd*. It is assumed that the `herd.yml` is located at the recommended config path.

For a full list of supported commands and options, run ```shepherd-herd --help``` and for more detail for each command ```shepherd-herd [COMMAND] --help```.

### Harvesting

Simultaneously start harvesting the connected energy sources on the nodes:

```Shell
shepherd-herd harvest -a cv20 -d 30 -o hrv.h5
```

or with long arguments as alternative

```Shell
shepherd-herd harvest --virtual-harvester cv20 --duration 30.0 --output-path hrv.h5
```

Explanation:

- uses cv20 algorithm as virtual harvester (constant voltage 2.0 V)
- duration is 30s
- file will be stored to `/var/shepherd/recordings/hrv.h5` and not forcefully overwritten if it already exists (add `-f` for that)
- nodes will sync up and start immediately (otherwise add `--no-start`)

For more harvesting algorithms see [virtual_harvester_fixture.yaml](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content/virtual_harvester_fixture.yaml).

### Emulation

Use the previously recorded harvest for emulating an energy environment for the attached sensor nodes and monitor their power consumption and GPIO events:

```Shell
shepherd-herd emulate --virtual-source BQ25504 -o emu.h5 hrv.h5
```

Explanation:

- duration (`-d`) will be that of input file (`hrv.h5`)
- target port A will be selected for current-monitoring and io-routing (implicit `--enable-io --io-port A --pwr-port A`)
- second target port will stay unpowered (add `--voltage-aux` for that)
- virtual source will be configured as BQ25504-Converter
- file will be stored to `/var/shepherd/recordings/emu.h5` and not forcefully overwritten if it already exists (add `-f` for that)
- nodes will sync up and start immediately (otherwise add `--no-start`)

For more virtual source models see [virtual_source_fixture.yaml](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/data_models/content/virtual_source_fixture.yaml).

### Generalized Task-Execution

An individual task or set of tasks can be generated from experiments via the [shepherd-core](https://pypi.org/project/shepherd-core/) of the [datalib](https://github.com/orgua/shepherd-datalib)

```Shell
shepherd-herd run experiment_file.yaml --attach
```

Explanation:

- a set of tasks is send to the individual sheep and executed there
- [tasks](https://github.com/orgua/shepherd-datalib/tree/main/shepherd_core/shepherd_core/data_models/task) currently range from

  - modifying firmware / patching a node-id,
  - flashing firmware to the targets,
  - running an emulation- or harvest-task
  - these individual tasks can be bundled up in observer-tasks -> a task-set for one sheep
  - these observer-tasks can be bundled up once more into testbed-tasks

- `online` means the program stays attached to the task and shows cli-output of the sheep, once the measurements are done


### File-distribution & retrieval

Recordings and config-files can be **distributed** to the remote nodes via:

```Shell
shepherd-herd distribute hrv.h5
```

The default remote path is `/var/shepherd/recordings/`. For security reasons there are only two allowed paths:

- `/var/shepherd/` for hdf5-recordings
- `/etc/shepherd/` for yaml-config-files

To retrieve the recordings from the shepherd nodes and store them locally on your machine in the current working directory (`./`):

```Shell
shepherd-herd retrieve hrv.h5 ./
```

Explanation:

- look for remote `/var/shepherd/recordings/hrv.h5` (when not issuing an absolute path)
- don't delete remote file (add `-d` for that)
- be sure measurement is done, otherwise you get a partial file (or add `--force-stop` to force it)
- files will be put in current working director (`./rec_[node-name].h5`, or `./[node-name]/hrv.h5` if you add `--separate`)
- you can add `--timestamp` to extend filename (`./rec_[timestamp]_[node-name].h5`)

### Start, check and stop Measurements

Manually **starting** a pre-configured measurement can be done via:

```Shell
shepherd-herd start
```

**Note 1**: configuration is loading locally from `/etc/shepherd/config.yml`.

**Note 2**: the start is not synchronized itself (you have to set `time_start` in config).

The current state of the measurement can be **checked** with (console printout and return code):

```Shell
shepherd-herd status
```

If the measurement runs indefinitely or something different came up, and you want to **stop** forcefully:

```Shell
shepherd-herd -l sheep1 stop
```

### Creating an Inventory

Creating an overview for what's running on the individual sheep / hosts. An inventory-file is created for each host.

```Shell
shepherd-herd inventorize ./
```

### Programming Targets (pru-programmer)

The integrated programmer allows flashing a firmware image to an MSP430FR (SBW) or nRF52 (SWD) and shares the interface with `shepherd-sheep`. This example writes the image `firmware_img.hex` to a MSP430 on target port B and its programming port 2:

```Shell
shepherd-herd program --mcu-type msp430 --target-port B --mcu-port 2 firmware_img.hex
```

To check available options and arguments call

```Shell
shepherd-herd program --help
```

The options default to:

- nRF52 as Target
- Target Port A
- Programming Port 1
- 3 V Target Supply
- 500 kbit/s


### Deprecated - Programming Targets (OpenOCD Interface)

Flash a firmware image `firmware_img.hex` that is stored on the local machine in your current working directory to the attached sensor nodes:

```Shell
shepherd-herd target flash firmware_img.hex
```

Reset the sensor nodes:

```Shell
shepherd-herd target reset
```

### Shutdown

Sheep can either be forced to power down completely or in this case reboot:

```Shell
shepherd-herd poweroff --restart
```

**NOTE**: Be sure to have physical access to the hardware for manually starting them again.

## Testbench

For testing `shepherd-herd` there must be a valid `herd.yml` at one of the three mentioned locations (look at [simplified usage](#Usage)) with accessible sheep-nodes (at least one). Navigate your host-shell into the package-folder `/shepherd/software/shepherd-herd/` and run the following commands for setup and running the testbench (~ 30 tests):

```Shell
pip3 install ./[tests]
pytest
```

## ToDo

- None
