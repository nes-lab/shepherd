import logging

import chromalog

log = logging.getLogger("Shp")
log.addHandler(logging.NullHandler())
verbose_level: int = 2


def get_verbose_level() -> int:
    return verbose_level


# TODO: use shepherd-core fn on next upload
def set_log_verbose_level(log_: logging.Logger, verbose: int) -> None:
    if verbose == 0:
        log_.setLevel(logging.ERROR)
        logging.basicConfig(level=logging.ERROR)
    elif verbose == 1:
        log_.setLevel(logging.WARNING)
    elif verbose == 2:
        log_.setLevel(logging.INFO)
    elif verbose > 2:
        log_.setLevel(logging.DEBUG)

    if verbose < 3:
        # reduce log-overhead when not debugging, also more user-friendly exceptions
        logging._srcfile = None
        logging.logThreads = 0
        logging.logProcesses = 0

    if verbose > 2:
        chromalog.basicConfig(format="%(name)s %(levelname)s: %(message)s")
    else:
        chromalog.basicConfig(format="%(message)s")  # reduce internals


def set_verbose_level(verbose: int) -> None:
    set_log_verbose_level(log, verbose)


set_verbose_level(2)
