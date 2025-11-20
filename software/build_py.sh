# dev-script for faster rebuilding (compared to ansible)
sudo systemctl stop shepherd-watchdog
sudo -E /usr/local/bin/uv tool install /opt/shepherd/software/python-package/. --upgrade --force
# alternative: sudo -E /usr/local/bin/uv tool upgrade --all
sudo -E /usr/local/bin/uv cache prune
sudo systemctl start shepherd-watchdog
# remove legacy cache-directories (might be used via ansible)
sudo rm -rf /home/jane/.cache/uv
sudo rm -rf /root/.cache/uv
# try via:
# sudo shepherd-sheep -v run /etc/shepherd/example_config_emulation.yaml
# for unittests install:
# sudo /usr/local/bin/uv pip install /opt/shepherd/software/python-package/. --upgrade
