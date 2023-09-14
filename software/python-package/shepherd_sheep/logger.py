import logging
from typing import Union

from shepherd_core.logger import set_log_verbose_level

log = logging.getLogger("Shp")
log.addHandler(logging.NullHandler())
verbosity_state: bool = False
log.setLevel(logging.INFO)


def get_verbosity() -> bool:
    return verbosity_state


def set_verbosity(state: Union[bool, int] = True, temporary: bool = False) -> None:
    if isinstance(state, bool) and not state:
        return
    if isinstance(state, int) and state < 3:
        return  # old format, will be replaced
    set_log_verbose_level(log, 3)
    if temporary:
        return
    global verbosity_state
    verbosity_state = True


def reset_verbosity() -> None:
    """Only done if it was increased temporary before"""
    if verbosity_state:
        return
    set_log_verbose_level(log, 2)
