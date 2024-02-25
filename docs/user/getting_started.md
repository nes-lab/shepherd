# Getting started

This section describes how to set up a shepherd-instance in a tethered setup.

## Prerequisites

To set up an instance of shepherd, you'll need to assemble a number of shepherd observers.

For each node, you'll need:

* BeagleBone (Green/Black)
* shepherd cape

  * for recording: harvesting transducer, e.g. solar cell
  * for emulation: target board

In addition, you'll need at least one SD-card with at least 4GB capacity. To setup linux and control the nodes a linux host-machine is recommended, but the terminal in macOS or WSL on Windows should work as well.

For details to the cape and additional hardware take a look at the [hardware section](./hardware.md).

The shepherd cape has a large number of small components. We suggest to send it to a PCB fab for assembly.

If you don't have the necessary resource or need assistance with getting the hardware manufactured, get in touch with the developers.

To connect the shepherd observers to each other for control, data collection and time-synchronization, you need to set up an Ethernet network.
The network should be as flat as possible, i.e. have a minimum number of switches. This prevents possible trouble and also improves time synchronization with ptp. For sub 1 us offsets a hardware accelerated switch (like the Cisco Catalyst Series) is beneficial.
By default, the BeagleBone Ubuntu image is configured to request an IP address by DHCP.
Therefore, your network should have a DHCP server.

## Hardware setup

Stack the cape on top of the BeagleBone. The two 23×2 headers of the cape plug into the BeagleBone (P8 and P9). Additionally, connect a harvesting source or target board to the cape.
Pay attention to the 2×2 harvesting header P6 on the cape. The corresponding signal labels are printed on the backside.
Stack the target PCB on top of the shepherd cape. The cape offers two ports P10 and P11 on the right side, additionally labeled A & B.

Provide all BeagleBones with power through either the USB type C port on the cape or the screw in connector right below it. Also connect the Ethernet ports to an Ethernet switch.
Using a PoE switch and corresponding power splitters can greatly reduce the cabling requirements. These can introduce noise into the system though. We designed an additional filtering regulator to allow input voltages up to 17 V that can be put in between.

The DHCP server and your machine (for installation/control) must be connected to the same network.


## Installation - Full Guide

Prepare the SD-cards.
If you plan to install the OS and shepherd software on the onboard EMMC flash, you can prepare one SD card and sequentially flash the nodes.
If you plan to install the OS and shepherd software on SD card, you have to prepare one SD card for every observer.
Depending on your choice, follow [the official instructions](https://elinux.org/BeagleBoardUbuntu#eMMC:_All_BeagleBone_Variants_with_eMMC) for **BeagleBone**. There is also a simplified and more detailed install-instruction in the following section.
Shepherd has been tested on [Ubuntu 22.04 LTS nightlies](https://rcn-ee.com/rootfs/ubuntu-armhf-22.04-console-v5.10-ti/), but might work with other Debian based distributions. Be sure to choose the `am335x`-image.

After installing the OS on the BeagleBones and booting them, determine their IP addresses.
If you know the subnet, you can use nmap from your machine, for example:

```Shell
nmap 192.168.178.0/24
```

Clone the shepherd repository to your machine:

```Shell
git clone https://github.com/orgua/shepherd.git
```

Add an inventory file in the `inventory` folder in the repository, assigning hostnames to the IP addresses of the shepherd observers.
Just start by editing the provided `inventory/herd.yml` example.
Pick a username that you want to use to log in to the system and assign as `ansible_user` variable.

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
  ptp_servers:
    hosts:
      sheep0:
  ptp_clients:
    hosts:
      sheep[1:30]:
```

:::{note}
Deployment supports roles that can be assigned directly in `herd.yml`.
The example above shows how to use them exemplary by setting up `sheep0` as a PTP-Server (`ptp_servers`) and the remaining nodes as Clients (`ptp_clients`).
Additional roles are called `ntp_clients`, `gps_clients` and `secured`. The last one is used to reduce the attack surface when used in a testbed by removing default accounts, open ports and other listeners.
:::

We'll use [Ansible](https://www.ansible.com/) to roll out a basic configuration to the nodes.
This includes setting the hostname, adding the user, allowing password-less ssh access and sudo without password.
Make sure that you have `Python >=3.6`, `pip` and `sshpass` installed on your machine.
Install `Ansible` with:

```Shell
pip3 install ansible
```

Navigate to the root-directory of the cloned shepherd-project.
Now run the *bootstrap* [Ansible playbook](https://docs.ansible.com/ansible/latest/user_guide/playbooks_intro.html) using the previously prepared inventory file:

```Shell
ansible-playbook deploy/bootstrap.yml
```

To streamline the installation process, the shepherd software is installed via ansible as well. The **deployment** playbook allows to easily automate this process on a group of nodes.

```Shell
ansible-playbook deploy/deploy.yml
```

On success, the nodes will reboot and should be ready for use, for example, using the *shepherd-herd* command line utility.

Further playbooks:

- `maintenance.yml` will handle updates, some configuration, remove clutter, improve ram-usage and boot-duration
- `fetch-hostkeys.yml` will copy keys from nodes, handy firmware resets, while keeping keys
- `setup_pwdless_ssh_for_host.yml` will deposit your machines' certificates on the nodes for future passwordless login
- `setup-dev-nfs.yml` establish a local network file system `/opt/shepherd-dev` for the nodes to access
- `setup-ext-storage.yml` will format and automount sd-card to `/var/shepherd/recordings`
- `dev_rebuild_sw.yml` hot-swaps pru-firmware (& kernel-module & py-package) by compiling and flashing without restart


## Installation - ready-to-use image

The following guide sets up a single observer by deploying a ready-to-use shepherd-image. The steps are more detailed and try to simplify the process for new users by cutting away the first instructions from the installation-guide in the previous section (up to shepherd-deploy with ansible). The guide is written for **Windows 10 (or newer)** as host. Linux users can easily adapt.

As new hardware and unknown software can be intimidating the steps were also [filmed and put on YouTube](https://youtu.be/UPEH7QODm8A) for comparing the progress.

First step is downloading the [current shepherd-image](https://drive.google.com/drive/folders/1HBD8D8gC8Zx3IYpiVImVOglhO_RTwGYx) and flashing it to a micro-sd-card with [balenaEtcher](https://etcher.balena.io/) in admin mode. Note that other tools like rufus probably don't work. Select the (still compressed `.img.xz`) image and choose the appropriate drive to begin flashing.

Insert the prepared sd-card into the Beaglebone, connect the device via ethernet-cable to your local network and finally power the Beaglebone with a USB-Wall-Charger or any other power source with 5V and at least 500 mA.

After power-up all **LEDs** should light up immediately for ~1s. From then on the outermost LED acts as a permanent heartbeat and the other 3 LEDs show different IO usage. Boot is finished when the LEDs stop being busy (~30s). After that you can log in.

How to connect? There are at least three options. In most cases you can access the system by using the hostname `sheep0`. If that does not work you can check the list of network-devices compiled by your routers webinterface. Alternatively you can scan your local IP-space with an ip scanner, in our example the `Angry IP Scanner` was used. Look for the hostname `sheep0` or the MAC-Vendor `Texas Instruments` in the list. **Be sure to use the IP-space of the correct network device of your host device - there might be more than one**.

Configure WSL on Windows with a Linux of your choice (we recommend a generic Ubuntu) or you can use the PowerShell if OpenSSH is installed as an optional feature (`windows > settings > apps > optional features`).

The commands below open a secure shell (ssh) to the Beaglebone. As it's an unknown device you have to accept a new fingerprint (or host key) **once** before entering the password `temppwd` of the Beaglebone. The console will also tell you the password while trying to log in. Notice how the current console-line now begins with `ubuntu@sheep0`. It means you are logged in and every issued command will be executed on the Beaglebone. To **quit the shell** type `exit` (remember for later).

```Shell
# login via host-name (requires local DNS)
ssh ubuntu@sheep0
# or IP-based (replace IP from your setup)
ssh ubuntu@10.0.0.10
```

Now it is recommended to check if ubuntu was indeed started from the sd-card as the Beaglebones own flash-storage could contain & boot an old OS.

```Shell
uname -a
# ⤷ the string should contain "4.19" & "focal"
ll /dev/mmc*
# ⤷ should show mmcblk0* (SD-Card) and mmcblk1* (internal eMMC)
mount
# ⤷ should show that /dev/mmcblk0p1 (SD-Card) is "/" (root-directory) usually on line 1
```

If the tests are positive it is safe to use the image as is from sd-card. Alternatively it is also possible to copy the OS to the internal eMMC for slightly improved performance. Note that the recommended eMMC flasher does not work, but `dd` can be used instead:

```Shell
sudo dd if=/dev/mmcblk0p1 of=/dev/mmcblk1p1
# ⤷ takes 10 - 20 min
```

After the command finishes shut down the Beaglebone either by `sudo shutdown now` or by pushing the button next to the ethernet socket. Remove the sd-card and boot the system back up again. Repeat the tests from above and make sure that the output matches except that `mount` now shows `mmcblk1p1` (eMMC) as root-directory.

For password-less entry & usage of the Beaglebone we prepared an `ansible playbook`. Make sure that you cloned the shepherd-repository locally and installed ansible (compare with general installation-guide from previous section) and also configured the `herd.yml` in consultation with the full installation guide.

```Shell
# execute in shepherd-repo on host
ansible-playbook ./deploy/setup_pwless_ssh_for_host.yml
```

Now that the Software is ready, a basic test of the shepherd-framework can be run. It is possible to start a pre-configured harvesting demo, even without a cape. This can be done either on the Beaglebone itself:

```Shell
sudo shepherd-sheep run --config /etc/shepherd/example_config_harvest.yaml
```

or on the host by installing and using [shepherd-herd](https://pypi.org/project/shepherd-herd/). After following the linked installation guide the same test can be run with:

```Shell
shepherd-herd start
```

Note that this will load a slightly different configuration-file (`/etc/shepherd/config.yaml`).
