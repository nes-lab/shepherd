# Services on Sheep

Beside the Sheep-CLI, the observers is managed by services

- `shepherd` reads & runs `/etc/shepherd/config.yml` when started
- `shepherd-rpc` offers the sheep-internals via zero-mq RPC-Server
- `shepherd-launcher` is used to control the node via the button / led interface
- `shepherd-watchdog` resets the capes watchdog-IC periodically

The first three services are disabled by default.

## Install

Copy to systemd-dir and enable if wanted

```Shell
sudo cp /opt/shepherd/software/python-package/services/shepherd* /etc/systemd/system/
sudo systemctl enable shepherd-watchdog
```

## Control

General control over the service

```Shell
systemctl enable shepherd
systemctl disable shepherd
```

```Shell
systemctl start shepherd
systemctl stop shepherd
systemctl restart shepherd
```

## Debug

Read console output with

```Shell
systemctl status shepherd
journalctl --follow -u shepherd
```
