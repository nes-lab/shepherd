import logging.handlers
import multiprocessing
import sys

import chromalog
from shepherd_core.logger import set_log_verbose_level

# Top-Level Package-logger
log = logging.getLogger("Shp")
log.setLevel(logging.DEBUG)
log.propagate = 0

# handler for CLI
console_handler = chromalog.ColorizingStreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Queue saves log for later putting it in hdf5-file
queue = multiprocessing.Queue(-1)
queue_handler = logging.handlers.QueueHandler(queue)
queue_handler.setLevel(logging.DEBUG)

# activate handlers
log.addHandler(console_handler)
log.addHandler(queue_handler)
verbosity_state: bool = False


def get_verbosity() -> bool:
    return verbosity_state


def set_verbosity(*, state: bool | int = True, temporary: bool = False) -> None:
    if isinstance(state, bool):
        # strange solution -> bool is also int, so it falls through below in elif
        if not state:
            return
    elif isinstance(state, int) and state < 3:
        return  # old format, will be replaced
    set_log_verbose_level(console_handler, 3)
    if temporary:
        return
    global verbosity_state  # noqa: PLW0603
    verbosity_state = True


def reset_verbosity() -> None:
    """Will reset only if it was increased temporary before."""
    if verbosity_state:
        return
    set_log_verbose_level(console_handler, 2)


def get_message_queue() -> multiprocessing.Queue:
    """Hand over queue.

    - read & delete with queue.get().
    - element.message is the text
    - len is queue.qsize()
    """
    return queue
