# Shepherd-Sheep

## Install Sheep

As `build_py.sh` in `/software` shows:

```Shell
sudo systemctl stop shepherd-watchdog
uv tool install /opt/shepherd/software/python-package/.
sudo systemctl start shepherd-watchdog
```

## Running unit-tests

As the snippet above installs the CLI-tools and not the testing environment we need to run:

```Shell
uv pip install /opt/shepherd/software/python-package/.[test]
# and to run the suite
sudo su
cd /opt/shepherd/software/python-package
pytest
```
