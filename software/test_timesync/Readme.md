# Sync-Analyzer

Collection of tools to analyze Sync-behavior, recorded with saleae logic pro

## Quick-HowTo

### Hardware

- connect channels + Ground
- activate sync mode (sudo shepherd-sheep pru sync)

### Capture with Logic 2 Software

- select used channels (Digital, NOT Analog)
- select highest sampling Rate (500 MS/s)
- Range: 3.3+ Volts
- Timer: 100s

### Prepare data for this tool 

- Logic 2 -> File -> Export Data
- select channels: 1-3 ???
- Time Range: All Time
- Format: CSV
- DON'T use ISO8601 timestamps
- Export and rename file to meaningful description

### Expected Data-Format

```csv
Time[s], Channel 0, Channel 1
0.000000000000000, 1, 1
7.642110550000000, 1, 0
```

Note: Name of channels is ignored

## Test-Requirements

- tests need 2-3 beaglebone running shepherd (sheep)
  - advantage of 3: one node can be ptp-server, the others are clients (server can have a sync-offset on our hardware-level)
- sheep are connected to a dhcp network (network under test)
- a separate host PC can
  - control the sheep via the herd-tool & ssh-sessions
  - record the sync-performance with a logic analyzer connected to each sheep
  - stress-test sheep and network with workloads

## Prepare the host

Ansible & herd-tool need python >= 3.10 and pipenv

```shell
python3 --version
pip install pipenv
```

Clone & enter shepherd-repo, then install and enter pipenv 

```shell
git clone https://github.com/orgua/shepherd
cd shepherd
pipenv install
pipenv shell
```

Adapt the herd-file that is located in `.\inventory\herd.yml` to reflect your network-setup. The connected sheep are communicating their MAC to the DHCP and also promote their name. The yaml-file will be used by ansible and the herd-tool as config. Example:

```yaml
sheep:
  hosts:
    sheep0:
      ansible_host: 192.168.1.100
    sheep1:
      ansible_host: 192.168.1.101
    sheep2:
      ansible_host: 192.168.1.102
```

If your host never connected to the sheep it's now time to enable passwordless entry. The easiest way would be via ansible-script. Note that the bootstrap-script also rewires the sheep-names according to your config.

```shell
ansible-playbook deploy/bootstrap.yml
```

You can test the connection now by executing something harmless on the sheep

```
shepherd-herd shell-cmd 'date'
```

Your host is now capable to command the sheep-herd.

For sync-analysis your also need the logic-software from [Saleae](https://www.saleae.com/downloads/)

## Hardware-Setup

- activate your desired network-setup (traffic, cpu-load, switch-configuration)
- small introduction into beaglebone
  - orientation: ICs / CPU visible, ETH-Connector facing left so the white font (silkscreen) on PCB is readable
  - there are two large connectors P8 on top, P9 on bottom. each has 46 pins, with pin 1 in the lower left corner - compare with silkscreen
  - P8 is our main-connector for the test. Pin 1 & 2 (left-most) are ground / GND
  - NOTE: there are (small) white markers on the PCB that indicate start of a decade
- small introduction into Saleae logic analyzer
  - channel-numbers are printed on the back-side
  - the removable connector-leads are color-coded and also have the channel-number printed on the end
  - all ground-cables are black without a channel-number printing
- connect logic analyzer to each sheep
  - GND goes to P8-01 or P8-02
  - Channel wire goes to P8-19 for the kernel-output
  - for debug another channel can be hooked up to P8-28 (pru-output)

## Software

Check current state of PTP

```Shell
shepherd-herd -v shell-cmd -s 'systemctl status phc2sys@eth0'
shepherd-herd -v shell-cmd -s 'systemctl status ptp4l@eth0'
```

Fixing time-sync problems can be solved be restarting the services and shepehrd-kernel-module

```shell
# when sheep remain unsynced
shepherd-herd -v shell-cmd -s 'systemctl restart ptp4l@eth0'
shepherd-herd -v shell-cmd -s 'systemctl restart phc2sys@eth0'
# signal on gpio missing (typically after clock changes significantly)
shepherd-herd fix
```

Creating CPU-Load

- run harvest first (this will create a measurement file)
- after that you can run emulation that uses that exact file as input
- Note: we exclude sheep0, as it is the ptp-server

```
shepherd-herd -v --limit sheep1,sheep2, run --attach .\software\test_timesync\config_harvest.yaml
shepherd-herd -v --limit sheep1,sheep2, run --attach .\software\test_timesync\config_emulation.yaml
```

Generating Network-traffic

## Measurement

General Notes

- PTP should be given some minutes to stabilize
- room-temperature should be stable, as clock-crystals react to that 
- think about recording a baseline first (undisturbed network)

Configure Logic 2 Software

- config under `Device Settings` (device-shaped symbol in top left corner of plot)
  - select connected channels -> usually `0 to 2`
  - select highest samplerate -> `500 MS/s`
  - select highest voltage-levels -> `3.3+ Volts`
  - set `Timer` to record for `200 s`

- start measurement (Blue Play-Button)

## Observations

- phc2sys reports suddenly high offsets (>100us)  
