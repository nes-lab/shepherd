# SHEpHERD: SyncHronized Energy Harvesting Emulator RecorDer

[![QA-Tests](https://github.com/nes-lab/shepherd/actions/workflows/quality_assurance.yaml/badge.svg)](https://github.com/nes-lab/shepherd/actions/workflows/quality_assurance.yaml)
[![Documentation](https://github.com/nes-lab/shepherd/actions/workflows/pages_update.yaml/badge.svg)](https://nes-lab.github.io/shepherd/)
[![Build Pru](https://github.com/nes-lab/shepherd/actions/workflows/fw_build_gcc.yaml/badge.svg)](https://github.com/nes-lab/shepherd/actions/workflows/fw_build_gcc.yaml)
[![Code Quality](https://www.codefactor.io/repository/github/nes-lab/shepherd/badge)](https://www.codefactor.io/repository/github/nes-lab/shepherd)
[![PyPIVersion](https://img.shields.io/pypi/v/shepherd_herd.svg)](https://pypi.org/project/shepherd_herd)
[![CodeStyle](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Testbed-Website**: <https://nes-lab.github.io/shepherd-nova>

**Python-Tools for Users**: <https://github.com/nes-lab/shepherd-tools>

**Documentation**: <https://nes-lab.github.io/shepherd>

**Main Project**: <https://github.com/nes-lab/shepherd>

**Targets-HW & -SW**: <https://github.com/nes-lab/shepherd-targets>

**WebAPI-Repo**: <https://github.com/nes-lab/shepherd-webapi>

**Dev-Documentation**: <https://github.com/orgua/shepherd-v2-planning>

---

Batteryless sensor nodes depend on harvesting energy from their environment.
Developing solutions involving groups of batteryless nodes requires a tool to analyze, understand and replicate spatio-temporal harvesting conditions.
*shepherd* is a testbed for the batteryless Internet of Things, allowing to record harvesting conditions at multiple points in space over time.
The recorded data can be replayed to attached wireless sensor nodes, examining their behavior under the constraints of spatio-temporal energy availability.

**Features**

 - High-speed, high resolution current and voltage sensing
 - Technology-agnostic: Currently, solar and kinetic energy harvesting are supported
 - Remote programming/debugging of ARM Cortex-M MCUs using Serial-Wire-Debug
 - High resolution, synchronized GPIO tracing
 - Configurable, constant voltage power supply for attached sensor nodes
 - Level-translated serial connection to the attached sensor nodes

For a detailed description see our [Paper](https://wwwpub.zih.tu-dresden.de/~mzimmerl/pubs/geissdoerfer19shepherd.pdf) or the [official documentation](https://nes-lab.github.io/shepherd/).

A *shepherd* instance consists of a group of spatially distributed *shepherd* nodes that are time-synchronized with each other.
Each *shepherd* node consists of a [BeagleBone](https://beagleboard.org/bone), the *shepherd* cape and either an energy harvesting source or a target MCU board to test.

This repository contains the hardware design files for the shepherd cape, the software running on each *shepherd* node as well as the tool to orchestrate a group of *shepherd* nodes connected to a network.

## Quickstart

Start by assembling your *shepherd* nodes, consisting of a BeagleBone Green/Black, a *shepherd* cape, a harvesting capelet and a target capelet.
The next step is to manually install the latest Ubuntu Linux on each BeagleBone.
You can install it to SD-card or the on-board eMMC flash, following [the official instructions](https://elinux.org/BeagleBoardUbuntu).
Make sure to follow the instructions for **BeagleBone**. Alternatively there are two more detailed guides in the [shepherd documentation](https://nes-lab.github.io/shepherd/user/getting_started.html).

The following instructions describe how to install the *shepherd* software on a group of *shepherd* nodes connected to an Ethernet network.
We assume that your local machine is connected to the same network, that the nodes have internet access and that you know the IP address of each node.

If you haven't done it yet, clone this repository to your local machine:

```shell
git clone https://github.com/nes-lab/shepherd.git
```

Next, install the tools used for installing and controlling the *shepherd* nodes.
We'll use [Ansible](https://www.ansible.com/) to remotely roll out the basic configuration to each *shepherd* node and *shepherd-herd* to orchestrate recording/emulation across all nodes.
The tools are hosted on `PyPI` and require Python version >= 3.6.
You'll also need to have `sshpass` installed on your machine, which is available through the package management system of all major distributions.
Install the tools using `pip`:

```shell
pip3 install ansible shepherd-herd
```

The `inventory/herd.yml` file shows an example of how to provide the host names and known IP addresses of your BeagleBones.
Adjust it to reflect your setup.
You can arbitrarily choose and assign the hostnames (sheep0, sheep1, in this example) and the ansible_user (jane in this example).
[**TODO:** update description with roles].

```yaml
sheep:
  hosts:
    sheep0:
        ansible_host: 192.168.1.100
    sheep1:
        ansible_host: 192.168.1.101
    sheep2:
        ansible_host: 192.168.1.102
  vars:
    ansible_user: jane
```

Now run the `bootstrap.yml` *Ansible* playbook, which sets the hostname, creates a user and enables passwordless ssh and sudo:

```shell
ansible-playbook deploy/bootstrap.yml
```

Finally, use the `deploy.yml` playbook to set up the *shepherd* software with the configured roles from inventory:

```shell
ansible-playbook deploy/deploy.yml
```

## Usage

Record two minutes of data:

```shell
shepherd-herd harvester -d 120 -o recording.h5 -a mppt_voc
```
The command starts the recording asynchronously and returns after all nodes have started recording.
While the nodes are still recording (indicated by blinking of LED 1 and 2), prepare a directory on your local machine:

```shell
mkdir ~/shepherd_recordings
```

After the nodes stop blinking, you can retrieve the data to analyze it on your local machine:

```shell
shepherd-herd retrieve recording.h5 ~/shepherd_recordings
```

For a detailed description of the [HDF5](https://en.wikipedia.org/wiki/Hierarchical_Data_Format) based data format, refer to the [corresponding documentation](https://shepherd-testbed.readthedocs.io/en/latest/user/data_format.html).

Finally, replay the previously recorded data to the attached sensor nodes, recording their power consumption:

```shell
shepherd-herd emulator -o consumption.h5 recording.h5
```

Try `shepherd-herd --help` or check out the documentation [here](https://shepherd-testbed.readthedocs.io/en/latest/user/cli.html#shepherd-herd) for a list of all options.

## Problems and Questions

If you experience issues or require additional features, please get in touch via e-mail or by creating an issue on GitHub. The issue-tab also gives an overview for current roadmaps and milestones.

## People

*shepherd* development is lead at the Networked Embedded Systems Lab at TU Dresden & TU Darmstadt as part of the DFG-funded project Next-IoT.

The following people have contributed to *shepherd*:

 - [Kai Geissdoerfer](https://www.researchgate.net/profile/Kai_Geissdoerfer)
 - [Mikolaj Chwalisz](https://www.tkn.tu-berlin.de/team/chwalisz/)
 - [Marco Zimmerling](https://wwwpub.zih.tu-dresden.de/~mzimmerl/)
 - [Justus Paulick](https://github.com/kugelbit)
 - [Boris Blokland](https://github.com/borro0)
 - [Jonas Kubicki](https://github.com/jonkub)
 - [Ingmar Splitt](https://github.com/nes-lab)
