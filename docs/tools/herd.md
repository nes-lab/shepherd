# Shepherd-Herd

```{include} ../../software/shepherd-herd/README.md
   :start-line: 2
   :end-line: 40
```

## Configuration

All `shepherd-herd` commands require the list of hosts on which to perform the requested action.

### Static Config

To simplify usage you should set up an ansible style, YAML-formatted inventory file named `herd.yml` in either of these directories (highest priority first):

- in your current working directory
- relative to your current working directory in `inventory/herd.yml`
- in your local home-directory `~/herd.yml`
- in your XDG config directory, typically `~/.config/shepherd-herd/herd.yml` (**recommendation**)
- in the system config path `/etc/shepherd/herd.yml`

Here is the example `herd.yml`-file in the `inventory` directory of the shepherd repository:

```{literalinclude} ../../inventory/herd.yml
:language: yaml
```

:::{note}
1. Only the `sheep:`-block is needed by the tool.
2. IP-Addresses can be omitted if network is set up to resolve host-names.
3. To find active observers a ping-sweep (in this example from .1 to .64) can be achieved with:

```Shell
nmap -sn 192.168.1.1-64
```
:::

After setting up the inventory, use `shepherd-herd` to check if all your nodes are responding correctly:

```Shell
shepherd-herd shell-cmd "echo 'hello'"
```

Or select individual sheep from the herd:

```Shell
shepherd-herd --limit sheep0,sheep2, shell-cmd "echo 'hello'"
```

### Dynamic Config

This list of hosts is provided with the `-i` option, that takes either the path to a file or a comma-separated list of hosts (compare Ansible `-i`).

```Shell
shepherd-herd -i sheep0,sheep1,sheep2, shell-cmd "echo 'hello'"
```

## Command-Line Interface

:::{note}
The tool has integrated help-functionality. For a full list of supported commands and options, run `shepherd-herd --help` and for more detail for each command `shepherd-herd [COMMAND] --help`.
:::

The command-line Interface is as follows:

```{eval-rst}
.. click:: shepherd_herd.herd_cli:cli
   :prog: shepherd-herd
   :nested: full
```

## Unittests

For testing `shepherd-herd` there must be a valid `herd.yml` at one of the mentioned locations (look at [](#configuration)) with accessible sheep-nodes (at least one).

1. Navigate your host-shell into the package-folder and
2. install dependencies
3. run the testbench (~ 30 tests):

```Shell
cd shepherd/software/shepherd-herd
pip3 install .[tests]
pytest
```
