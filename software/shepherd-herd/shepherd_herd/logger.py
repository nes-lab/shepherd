import logging

from shepherd_core.logger import get_verbose_level
from shepherd_core.logger import set_log_verbose_level

logger = logging.getLogger("shepherd-herd")
logger.addHandler(logging.NullHandler())
set_log_verbose_level(logger, 2)
# Note: defined here to avoid circular import
# TODO: add queue and also save log to file


def get_verbosity() -> bool:
    return get_verbose_level() >= 3


def activate_verbosity() -> None:
    set_log_verbose_level(logger, 3)
