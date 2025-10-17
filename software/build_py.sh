# dev-script for faster rebuilding (compared to ansible)
sudo systemctl stop shepherd-watchdog
sudo rm -rf /home/jane/.local/share/uv/tools/shepherd-sheep/lib/python3.11/site-packages/shepherd_sheep/__pycache__
sudo rm -rf /home/jane/.local/share/uv/tools/shepherd-sheep/lib/python3.11/site-packages/shepherd_watchdog/__pycache__
sudo rm -rf /home/jane/.local/share/uv/tools/shepherd-sheep/lib/python3.11/site-packages/shepherd_core/__pycache__
sudo rm -rf /home/jane/.local/share/uv/tools/shepherd-sheep/lib/python3.11/site-packages/shepherd_core/testbed_client/__pycache__
sudo rm -rf /home/jane/.local/share/uv/tools/shepherd-sheep/lib/python3.11/site-packages/shepherd_core/vsource/__pycache__
sudo rm -rf /home/jane/.local/share/uv/tools/shepherd-sheep/lib/python3.11/site-packages/shepherd_core/inventory/__pycache__
sudo rm -rf /home/jane/.venv/lib/python3.11/site-packages/shepherd_sheep/__pycache__
sudo rm -rf /home/jane/.venv/lib/python3.11/site-packages/shepherd_watchdog/__pycache__
sudo rm -rf /home/jane/.venv/lib/python3.11/site-packages/shepherd_core/vsource/__pycache__
sudo rm -rf /home/jane/.venv/lib/python3.11/site-packages/shepherd_core/__pycache__
# sudo rm -rf /home/jane/.local/share/uv/tools/shepherd-sheep/lib
# TODO: last can replace the 3 before
uv tool install /opt/shepherd/software/python-package/.
uv cache prune
sudo systemctl start shepherd-watchdog
# sudo shepherd-sheep -v run /etc/shepherd/example_config_emulation.yaml
