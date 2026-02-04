# /etc/profile.d/shepherd.sh: custom profile (generalized & more-powerful .bashrc)
# -> only root needs an extra entry in /root/.bashrc
#    . '/etc/profile.d/shepherd.sh'

# useful lines from .bashrc
export LS_OPTIONS='--color=auto'
alias ll='ls $LS_OPTIONS -l'

# hint to venv -> deactivated as venv-approach is not used ATM
# export PATH=$PATH:/home/jane/.venv/bin

# uv config -> elevation via 'sudo -E uv ...'
export UV_TOOL_BIN_DIR=/usr/local/bin
export UV_CACHE_DIR=/tmp/uv-cache

# directly start in dev-env
cd /opt/shepherd/software
