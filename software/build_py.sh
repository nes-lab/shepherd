# dev-script for faster rebuilding (compared to ansible)
# update uv with:
# sudo pip install uv --upgrade --break-system-packages
sudo systemctl stop shepherd-watchdog
sudo -E /usr/local/bin/uv pip install /opt/shepherd/software/python-package/.[test] --upgrade --system --break-system-packages
# will install in /usr/local/bin/shepherd-sheep, check via 'whereis shepherd-sheep'
sudo -E /usr/local/bin/uv cache prune
sudo /usr/local/bin/uv cache prune
sudo systemctl start shepherd-watchdog
# remove legacy cache-directories (might be used via ansible)
sudo rm -rf /home/jane/.cache/uv
sudo rm -rf /root/.cache/uv
# check if working via:
# sudo shepherd-sheep -v run /etc/shepherd/example_config_emulation.yaml
