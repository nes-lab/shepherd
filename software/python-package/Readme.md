# Shepherd-Sheep

## Install Sheep

As `build_py.sh` in `/software` shows:

```Shell
sudo systemctl stop shepherd-watchdog
uv tool install /opt/shepherd/software/python-package/.
sudo systemctl start shepherd-watchdog
```

## Running unit-tests

With the recent 2025 restrictions of debian, system-level is not usable for user-controlled python-packages.
As the snippet above installs the CLI-tools and not the testing environment we need to run:

```Shell
uv pip install /opt/shepherd/software/python-package/.[test] -U
# and to run the suite
sudo su
cd /opt/shepherd/software/python-package
pytest

# or this alternative (without sudo su)
cd /opt/shepherd/software/python-package
whereis pytest
# should respond with: /home/jane/.venv/bin/pytest
sudo -E /home/jane/.venv/bin/pytest
```
