# Shepherd-Herd

```{literalinclude} ../../software/shepherd-herd/README.md
   :lines: 2-40
```

## Configuration

All `shepherd-herd` commands require the list of hosts on which to perform the requested action.

To find active nodes a ping-sweep (in this example from .1 to .64) can be achieved with:

```Shell
nmap -sn 192.168.1.1-64
```

### Static

To simplify usage you should set up an ansible style, YAML-formatted inventory file named `herd.yml` in either of these directories (highest priority first):

- relative to your current working directory `herd.yml`
- relative to your current working directory in `inventory/herd.yml`
- in your local home-directory `~/herd.yml`
- in the config path `/etc/shepherd/herd.yml` (**recommendation**)

Here is the example `herd.yml`-file in the `inventory` directory of the shepherd repository:

```{literalinclude} ../../inventory/herd.yml
:language: yaml
```

Only the `sheep:`-block is needed by the tool.

After setting up the inventory, use `shepherd-herd` to check if all your nodes are responding correctly:

```Shell
shepherd-herd -i herd.yml shell-cmd "echo 'hello'"
```

:::{note}
If you wish to 


### Dynamic

This list of hosts is provided with the `-i` option, that takes either the path to a file or a comma-separated list of hosts (compare Ansible `-i`).

## Command-Line Interface

The command-line Interface is as follows:

```{eval-rst}
.. click:: shepherd_herd.herd_cli:cli
   :prog: shepherd-herd
   :nested: full
```

## API
