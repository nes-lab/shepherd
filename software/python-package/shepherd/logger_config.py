import logging

import chromalog

# Set default logging handler to avoid "No handler found" warnings.
chromalog.basicConfig(format="%(message)s")
logger = logging.getLogger("shp")
logger.addHandler(logging.NullHandler())
verbose_level: int = 0


def get_verbose_level() -> int:
    global verbose_level
    return verbose_level


def set_verbose_level(verbose: int) -> None:
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
        chromalog.basicConfig(format="%(name)s %(levelname)s: %(message)s")
    else:
        chromalog.basicConfig(format="%(message)s")


# short reminder for format-strings:
# %s    string
# %d    decimal
# %f    float
# %o    decimal as octal
# %x    decimal as hex
#
# %05d  pad right (aligned with 5chars)
# %-05d pad left (left aligned)
# %06.2f    6chars float, including dec point, with 2 chars after
# %.5s  truncate to 5 chars
