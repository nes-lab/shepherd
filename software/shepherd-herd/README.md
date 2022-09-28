# shepherd-herd

*shepherd-herd* is the command line utility for controlling a group of shepherd nodes remotely through an IP-based network.


## Installation

*shepherd-herd* is a pure python package and available on PyPI.
Use your python package manager to install it.
For example, using pip:

```Shell
pip3 install shepherd-herd
```

For install from local sources:

```Shell
cd shepherd/software/shepherd-herd/
pip3 install ./
```

## Usage

All *shepherd-herd* commands require the list of hosts on which to perform the requested action.
This list of hosts is provided with the `-i` option, that takes either the path to a file or a comma-separated list of hosts (compare Ansible `-i`).

For example, save the following file in your current working directory as an ansible style, YAML-formatted inventory file named `herd.yml`.

```
sheep:
  hosts:
    sheep0:
    sheep1:
    sheep2:
  vars:
    ansible_user: jane
```

Then use shepherd-herd to check if all your nodes are up:

```Shell
shepherd-herd -i herd.yml run echo 'hello'
```

Or, equivalently define the list of hosts on the command line

```Shell
shepherd-herd -i sheep0,sheep1,sheep2, run echo 'hello'
```

To **simplify usage** you should set up the `herd.yml` in either of these directories (with falling lookup priority):

- relative to your current working directory in `inventory/herd.yml`
- in your local home-directory `~/herd.yml`
- in the **config path** `/etc/shepherd/herd.yml` (**recommendation**)

From then on you can just call:

```Shell
shepherd-herd run echo 'hello'
```

Or select individual sheep from the herd:

```Shell
shepherd-herd --limit sheep0,sheep2, run echo 'hello'
```

## Examples

Here, we just provide a selected set of examples of how to use *shepherd-herd*. It is assumed that the `herd.yml` is located at the recommended config path.

For a full list of supported commands and options, run ```shepherd-herd --help``` and for more detail for each command ```shepherd-herd [COMMAND] --help```.

### Harvesting

Simultaneously start harvesting the connected energy sources on the nodes:

```Shell
shepherd-herd harvester -a cv33 -d 30 -o rec.h5
```

or with long arguments as alternative

```Shell
shepherd-herd harvester --algorithm cv20 --duration 30.0 --output_path rec.h5
```

Explanation:

- uses cv33 algorithm (constant voltage 2.0 V)
- duration is 30s
- file will be stored to `/var/shepherd/recordings/rec.h5` and not forcefully overwritten if it already exists (add `-f` for that)
- nodes will sync up and start immediately (otherwise add `--no-start`)

For more harvesting algorithms see [virtual_harvester_defs.yml](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd/virtual_harvester_defs.yml).

### Emulation

Use the previously recorded harvest for emulating an energy environment for the attached sensor nodes and monitor their power consumption and GPIO events:

```Shell
shepherd-herd emulator --virtsource BQ25504 -o emu.h5 rec.h5
```

Explanation:

- duration (`-d`) will be that of input file (`rec.h5`)
- target port A will be selected for monitoring and io-routing (implicit `--enable_io --io_sel_taget_a --pwr_sel_target_a`)
- second target port will stay unpowered (add `--aux_voltage` for that)
- virtual source will be configured as BQ25504-Converter
- file will be stored to `/var/shepherd/recordings/emu.h5` and not forcefully overwritten if it already exists (add `-f` for that)
- nodes will sync up and start immediately (otherwise add `--no-start`)

For more virtual source models see [virtual_source_defs.yml](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd/virtual_source_defs.yml).

### Data retrieval

After recording is done, retrieve the data from all nodes to your local machine for analysis:

To retrieve the recordings from the shepherd nodes and store them locally on your machine in the current working directory (`./`):

```Shell
shepherd-herd retrieve rec.h5 ./
```

Explanation:

- look for remote `/var/shepherd/recordings/rec.h5` (when not issuing an absolute path)
- don't delete remote file (add `-d` for that)
- be sure measurement is done, otherwise you get a partial file (or add `--stop` to force it)
- files will be put in current working director (`./[node-name]/rec.h5`)
- you can add `--timestamp` to extend filename

### Stop Measurement (forcefully)

If the measurement runs indefinitely or something different came up and you want to stop:

```Shell
shepherd-herd -l sheep1 stop
```

### Programming Targets

Flash a firmware image `firmware_img.bin` that is stored on the local machine in your current working directory to the attached sensor nodes:

```Shell
shepherd-herd target flash firmware_img.bin
```

Reset the sensor nodes:

```Shell
shepherd-herd target reset
```

### Shutdown

Sheep can either be forced to power down completely or in this case reboot:

```Shell
shepherd-herd poweroff --reset
```

## Testbench

For testing `shepherd-herd` there must be a valid `herd.yml` at one of the three mentioned locations (look at [simplified usage](#Usage)) with accessible sheep-nodes. Navigate your shell into the package-folder `/shepherd/software/shepherd-herd/` and run:

```Shell
pytest
```

TODO: add programming-option
