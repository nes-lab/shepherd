# Create a Shepherd-ISO

## Prereqs

- download image (Debian 12 recommended), see [](../user/getting_started.md)
- burn to micro-SD card (i.e. with balena etcher)
- activate flasher in `/boot/uEnv.txt`
- have a beaglebone ready & connected to a network
- insert SD-Card and boot beaglebone -> image will be copied to internal eMMC
- test the code

## Switch Cape-Version

For ansible setup:

- ansible `roles/sheep/defaults/main.yml` has hardcoded `sheep_cape_hw_var`

For an active installation:

- change device-tree loaded during boot in `/boot/uEnv.txt` (24A0 or 25A0)
- update pru-firmwares (modify envVar in `./software/build_pru.sh` and run script)
- python pulls cape-version from EEPROM automatically or defaults to the newest version

## Custom Install

- adapt your herd.yaml to point to the one beaglebone, activate roles for sheep and ptp-client
- run ansible `deploy/bootstrap.yml`
- run ansible `deploy/deploy.yml`
- distribute ssh keys of server & admin (`NESLAB/2026-misc/authorized_keys`)
- run ansible `deploy/dev_acquire_image.yml`
- pull image with command given by `deploy/dev_acquire_image.yml`
- burn image to SD and check if it boots properly

useful commands

```shell
cat /etc/debian_version
# ⤷ currently shows debian 12.13
sudo /usr/sbin/ntpdate -b -s -u pool.ntp.org
# ⤷ for manual timesync
sudo systemctl status phc2sys@eth0
sudo systemctl status ptp4l@eth0
# ⤷ for stopping / starting sync systems
ip a
# ⤷ determine current IP
```

## Distribution to other nodes

- burn image to other SD-cards
- activate sysrqd
- ansible `deploy/setup_testbed_observer.yml` (secure, MAC broadcasting, NFS mounting)
- grow partition? growpart /dev/mmcblk1p1 -> add to observer-role?

Activate [SysRqd](https://github.com/jd/sysrqd)

```Shell
shepherd-herd shell "sudo apt install sysrqd -y"
shepherd-herd shell "echo 'YOUR_COMPLEX_CUSTOM_PASSWORD' > ~/sysrqd.secret"
shepherd-herd shell "sudo mv ~/sysrqd.secret /etc/"
shepherd-herd shell "sudo chmod 0600 /etc/sysrqd.secret"

shepherd-herd shell "sudo systemctl restart sysrqd"
shepherd-herd shell "sudo systemctl status sysrqd"

telnet 192.168.165.200 4094  --> only working inside sheep-network
> PW
> b  (for hard reboot)

to exit: ctrl + altgr + ] -> on telnet-console: quit
```
