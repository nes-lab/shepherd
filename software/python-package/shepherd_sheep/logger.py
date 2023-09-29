import logging.handlers
import multiprocessing
import sys
from typing import Union

from shepherd_core.logger import set_log_verbose_level

log = logging.getLogger("Shp")
queue = multiprocessing.Queue(-1)
qhdl = logging.handlers.QueueHandler(queue)
log.addHandler(qhdl)
verbosity_state: bool = False
log.setLevel(logging.INFO)
qhdl.setLevel(logging.DEBUG)


def get_verbosity() -> bool:
    return verbosity_state


def set_verbosity(state: Union[bool, int] = True, temporary: bool = False) -> None:
    if isinstance(state, bool):
        # strange solution -> bool is also int, so it falls through below in elif
        if not state:
            return
    elif isinstance(state, int) and state < 3:
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


def get_message_queue() -> multiprocessing.Queue:
    """
    read & delete with queue.get() -> element.message is the text
    len is queue.qsize()
    """
    return queue
