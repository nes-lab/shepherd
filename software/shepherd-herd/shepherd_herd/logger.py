import logging

from shepherd_core.logger import set_log_verbose_level

logger = logging.getLogger("shepherd-herd")
verbose_state: bool = False
logger.addHandler(logging.NullHandler())
set_log_verbose_level(logger, 2)
# Note: defined here to avoid circular import


def get_verbose_state() -> bool:
    return verbose_state


def activate_verbose() -> None:
    global verbose_state
    verbose_state = True
    set_log_verbose_level(logger, 3)
