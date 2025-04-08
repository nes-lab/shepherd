# dev-script for faster rebuilding (compared to ansible)
sudo pip uninstall shepherd-sheep --break-system-packages --yes
sudo pip install /opt/shepherd/software/python-package/. -U --break-system-packages
#
sudo pip install pydantic click -U --break-system-packages
# sudo shepherd-sheep -v run /etc/shepherd/example_config_emulation.yaml
