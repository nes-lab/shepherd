import logging
from typing import Union

from shepherd_core.logger import set_log_verbose_level

logger = logging.getLogger("shepherd-herd")
verbosity_state: bool = False
logger.addHandler(logging.NullHandler())
set_log_verbose_level(logger, 2)
# Note: defined here to avoid circular import
# TODO: add queue and also save log to file


def get_verbosity() -> bool:
    return verbosity_state


def set_verbosity(state: Union[bool, int] = True) -> None:
    if isinstance(state, bool):
        # strange solution -> bool is also int, so it falls through below in elif
        if not state:
            return
    elif isinstance(state, int) and state < 3:
        return  # old format, will be replaced
    set_log_verbose_level(logger, 3)
    global verbosity_state
    verbosity_state = True
