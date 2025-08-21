# dev-script for faster rebuilding (compared to ansible)
uv tool install /opt/shepherd/software/python-package/.
uv cache prune
# sudo shepherd-sheep -v run /etc/shepherd/example_config_emulation.yaml
