# -*- coding: utf-8 -*-
import logging
from typing import NoReturn

# Set default logging handler to avoid "No handler found" warnings.
logger = logging.getLogger("shp")
logger.addHandler(logging.NullHandler())
verbose_level: int = 0


def get_verbose_level() -> int:
    global verbose_level
    return verbose_level


def set_verbose_level(verbose: int) -> NoReturn:
    # performance-critical, <4 reduces chatter during main-loop
    # needed to differentiate DEBUG-Modes -> '3' only ON during init, '4' also ON during main-run
    global verbose_level
    verbose_level = verbose

    if verbose == 0:
        logger.setLevel(logging.ERROR)
        logging.basicConfig(level=logging.ERROR)
        # TODO: replace with more general logging.basicConfig(level=logging.ERROR)
    elif verbose == 1:
        logger.setLevel(logging.WARNING)
    elif verbose == 2:
        logger.setLevel(logging.INFO)
    elif verbose > 2:
        logger.setLevel(logging.DEBUG)

    if verbose < 3:
        # reduce log-overhead when not debugging, also more user-friendly exceptions
        logging._srcfile = None
        logging.logThreads = 0
        logging.logProcesses = 0

    if verbose > 2:
        logging.basicConfig(format="%(name)s %(levelname)s: %(message)s")
    else:
        logging.basicConfig(format="%(message)s")
