# Kernel Dev

A good starting point for online literature:

- [Elixir Cross Referencer](https://elixir.bootlin.com/linux/v4.19.94/A/ident/memremap)
  - good for finding from where to include functionality, also configuration is explained in the source
- [Doc for kernel 4.19](https://www.kernel.org/doc/html/v4.19/core-api/index.html#)
  - most basic APIs are described there, including some good practices
- free Book [Linux Device Drivers](https://lwn.net/Kernel/LDD3/)

## Kernel 6.1

- https://elixir.bootlin.com/linux/v6.1.83/A/ident/memremap
- https://www.kernel.org/doc/html/v6.1/core-api/index.html#

DevLog for moving codebase to v6.1: https://github.com/nes-lab/shepherd/issues/11

## Kernel 6.18

## Debugging

Show if device-tree was loaded:

```shell
ls /sys/bus/platform/drivers/shepherd/
# 4a300000.pruss:shepherd  bind  module  uevent  unbind
ls /sys/bus/platform/devices/
# RPROC
#   4a300000.pruss
#	4a326004.pruss-soc-bus
#	4a334000.pru
#   4a338000.pru
# UIO:
#	4a300000.pruss
#	NO Shepherd
ls /proc/device-tree/chosen/overlays/
ls /proc/device-tree/
```

Steps that show failing load of kModule

```shell
dmesg | grep -i remote
# [    2.991034] remoteproc remoteproc0: wkup_m3 is available
# [   46.305514] systemd[1]: Reached target remote-fs.target - Remote File Systems.
# [   73.508576] remoteproc remoteproc0: powering up wkup_m3
# [   73.508629] remoteproc remoteproc0: Booting fw image am335x-pm-firmware.elf, size 217148
# [   73.508900] remoteproc remoteproc0: remote processor wkup_m3 is now up
# [   76.656366] remoteproc remoteproc1: 4a334000.pru is available
# [   76.659174] remoteproc remoteproc2: 4a338000.pru is available
dmesg | grep -i sheph
dmesg | grep -i shp
dmesg | grep -i overlay
```
