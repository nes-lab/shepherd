# dev-script for faster rebuilding (compared to ansible)
sudo systemctl stop shepherd-watchdog
uv tool install /opt/shepherd/software/python-package/.
uv cache prune
sudo systemctl start shepherd-watchdog
# sudo shepherd-sheep -v run /etc/shepherd/example_config_emulation.yaml
