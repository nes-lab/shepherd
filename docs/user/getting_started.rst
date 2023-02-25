Getting started
===============

This section describes how to setup an instance of shepherd in a tethered setup.

Prerequisites
-------------

To setup an instance of shepherd, you'll need to assemble a number of shepherd nodes.

For each shepherd node, you'll need:

* BeagleBone (Green/Black)
* shepherd cape

  * for recording: harvesting transducer, e.g. solar capelet and solar cell
  * for emulation: target capelet

In addition, you'll need at least one SD-card with at least 4GB capacity. To setup linux and control the nodes a linux host-machine is recommended, but the terminal in macOS or WSL for Windows should work as well.

For the cape and capelets take a look at the `hardware design files <https://github.com/orgua/shepherd/tree/main/hardware>`_.
Shepherd version 2 hardware is currently under development, see the separate `repository <https://github.com/orgua/shepherd_v2_planning/tree/main/PCBs>`_.
The capelets can mostly be soldered by hand (except the target pcb).
The shepherd cape has a large number of small components and we suggest to send it to a PCB fab for assembly.

If you don't have the necessary resource or need assistance with getting the hardware manufactured, get in touch with the developers.

To connect the shepherd nodes to each other for control, data collection and time-synchronization, you need to setup an Ethernet network.
The network should be as flat as possible, i.e. have a minimum number of switches. This prevents possible trouble and also improves time synchronization with ptp. For sub 1 us offsets a hardware accelerated switch (like the Cisco Catalyst Series) is beneficial.
By default, the BeagleBone Ubuntu image is configured to request an IP address by DHCP.
Therefore your network should have a DHCP server.

Hardware setup
--------------

Stack the cape on top of the BeagleBone. The two 23x2 headers of the cape plug into the BeagleBone (P8 and P9).
Stack the harvesting capelet on top of the shepherd cape. The capelet is left-aligned on the same 23x2, but using just two 11x2 headers. Pay attention to the 2x2 header P6 (on the cape) for the correct orientation.

Stack the target capelet on top of the shepherd cape. The cape offers two ports P10 and P11 on the right side, also labeled as A & B.

Provide all BeagleBones with power through the micro USB ports and connect their Ethernet ports to an Ethernet switch.
Using a PoE switch and corresponding micro USB power splitters can greatly reduce the cabling requirements. These can introduce noise into the system though.
Same applies to the power-output of the Beaglebone. Therefore the cape offers an additional power-input in the lower left corner. It is able to power the whole shepherd node.
**Make sure** the jumper near the power terminal J1 is set according to the input source (up for micro USB, down by power terminal).

The DHCP server and your machine (for installation/control) must be connected to the same network.


Installation
------------

Prepare the SD-cards.
If you plan to install the OS and shepherd software on the onboard EMMC flash, you can prepare one SD card and sequentially flash the nodes.
If you plan to install the OS and shepherd software on SD card, you have to prepare one SD card for every shepherd node.
Depending on your choice, follow `the official instructions <https://elinux.org/BeagleBoardUbuntu#eMMC:_All_BeagleBone_Variants_with_eMMC>`_ for **BeagleBone**. There is also a simplified and more detailed install-instruction in the following section.
Shepherd has been tested on Ubuntu 18.04 LTS (image updated 2020-03-12), but might work with other Debian based distributions.

**Note from 2022-05**: the last official release is getting quite old. Latest `nightlies of Ubuntu <https://rcn-ee.com/rootfs/ubuntu-armhf-focal-minimal/>`_ (navigate to newer date and choose ``am335x-[distro]-console-armhf-[date]-4gb.img.xz`` inside), work as well and offer more performant software.

After installing the OS on the BeagleBones and booting them, find out their IP addresses.
If you know the subnet, you can use nmap from your machine, for example:

.. code-block:: bash

    nmap 192.168.178.0/24

Clone the shepherd repository to your machine:

.. code-block:: bash

    git clone https://github.com/orgua/shepherd.git


Add an inventory file in the ``inventory`` folder in the repository, assigning hostnames to the IP addresses of the shepherd nodes.
Just start by editing the provided ``inventory/herd.yml`` example.
Pick a username that you want to use to login to the nodes and assign as ``ansible_user`` variable.
[**TODO:** update description with roles].

.. code-block:: yaml

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

We'll use `Ansible <https://www.ansible.com/>`_ to roll out a basic configuration to the nodes.
This includes setting the hostname, adding the user, allowing password-less ssh access and sudo without password.
Make sure that you have ``Python >=3.6``, ``pip`` and ``sshpass`` installed on your machine.
Install ``Ansible`` with:

.. code-block:: bash

    pip3 install ansible

Navigate to the root-directory of the cloned shepherd-project.
Now run the *bootstrap* `Ansible playbook <https://docs.ansible.com/ansible/latest/user_guide/playbooks_intro.html>`_ using the previously prepared inventory file:

.. code-block:: bash

    ansible-playbook deploy/bootstrap.yml

To streamline the installation process, the shepherd software is installed via ansible as well. The *deploy* playbook allows to easily automate this process on a group of nodes.

.. code-block:: bash

    ansible-playbook deploy/deploy.yml

On success, the nodes will reboot and should be ready for use, for example, using the *shepherd-herd* command line utility.

Further playbooks:

    - ``setup_linux_configuration.yml`` will handle updates, some configuration, remove clutter, improve ram-usage and boot-duration
    - ``setup_linux_performance.yml`` handles additional speed-improving changes
    - ``fetch-hostkeys.yml`` will copy keys from nodes, handy for reflashing image, while keeping keys
    - ``setup_pwdless_ssh_for_host.yml`` will deposit your machines' certificates on the nodes for future passwordless login
    - ``setup-dev-nfs.yml`` establish a local network file system ``/opt/shepherd-dev`` for the nodes to access
    - ``setup-ext-storage.yml`` will format and automount sd-card to ''/var/shepherd/recordings''
    - ``dev_rebuild_sw.yml`` hot-swaps pru-firmware (& kernel-module & py-package) by compiling and flashing without restart

.. _install-simple:

Installation - simplified & more detailed
------------------------------------------

The following steps set up a single shepherd-node by using a ready-to-use shepherd-image. It cuts away the first instructions from the installation-guide in the previous section (up to shepherd-deploy with ansible). The guide is written for **Windows 10 (or newer)** as host, but linux users can easily adapt, as mostly WSL is used.

As new hardware and unknown software can be intimidating the steps were also `filmed and put on youtube <https://youtu.be/UPEH7QODm8A>`_ for comparing the progress.

First step is downloading the `current shepherd-image <https://drive.google.com/drive/folders/1HBD8D8gC8Zx3IYpiVImVOglhO_RTwGYx>`_ and flashing it to a micro-sd-card with balenaEtcher in admin mode (note: other tools like rufus probably don't work). Select the (still compressed ``.img.xz``) image and choose the drive before flashing.

Insert the sd-card into the Beaglebone, connect the device via ethernet-cable to your router and finally power the Beaglebone with a USB-Wall-Charger or any other power source with 5V and at least 500 mA.

After power-up all **LEDs** should light up for ~1s. From then on the outermost LED acts as a permanent heartbeat and the other 3 LEDs show different IO usage. Boot is finished when the LEDs stop being busy (~30s).

In most cases you can access the Beaglebone by using the hostname ``sheep0``. If that does not work you can check the list of network-devices compiled by your routers webinterface. Alternatively you can scan your local IP-space with an ip scanner, in our example the ``Angry IP Scanner`` was used. Look for the hostname ``sheep0`` or the MAC-Vendor ``Texas Instruments`` in the list. Be sure to use the IP-space of the correct network device.

Configure WSL on Windows with a generic Ubuntu or just use the PowerShell if OpenSSH is installed as an optional feature (``settings > apps > optional features``).

The commands below open a secure shell (ssh) to the Beaglebone. You have to accept a new fingerprint once before entering the password ``temppwd`` of the Beaglebone. The console will also tell you the password. Notice how the current console-line now begins with ``ubuntu@sheep0``. It means you are logged in and every issued command will be executed on the Beaglebone. To **quit the shell** type ``exit``.

.. code-block:: bash

    ssh ubuntu@sheep0
    # or IP-based (replace IP from your setup)
    ssh ubuntu@10.0.0.10

Now it is recommended to check if ubuntu was indeed started from the sd-card as the Beaglebone could contain an old OS.

.. code-block:: bash

    uname -a
    # -> the string should contain "4.19" & "focal"
    ll /dev/mmc*
    # -> should show mmcblk0* (SD-Card) and mmcblk1* (internal eMMC)
    mount
    # -> should show that /dev/mmcblk0p1 (SD-Card) is "/" (root-directory) usually on line 1

If the tests are positive it is safe to use the image as is from sd-card. Alternatively it is also possible to copy the OS to the internal eMMC for improved performance. Note that the usual eMMC flasher does not work and ``dd`` must be used instead:

.. code-block:: bash

    sudo dd if=/dev/mmcblk0p1 of=/dev/mmcblk1p1
    # -> takes 10 - 20 min

After the command finishes shut down the Beaglebone either by ``sudo shutdown now`` or by pushing the button next to the network socket. Remove the sd-card and boot the system back up again. Repeat the tests from above and make sure that the output matches except that ``mount`` now shows mmcblk1p1 (eMMC) as root-directory.

For password-less entry & usage of the Beaglebone we prepared an ``ansible playbook``. Make sure that you cloned the shepherd-repository and installed ansible (compare with general installation-guide from previous section).

.. code-block:: bash

    # execute in shepherd-repo on host
    ansible-playbook ./deploy/setup_pwless_ssh_for_host.yml
