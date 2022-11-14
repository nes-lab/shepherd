import logging

# consoleHandler = logging.StreamHandler()
logger = logging.getLogger("shp.calTool")
# logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)


def set_verbose_level(verbose: int = 2) -> None:
    if verbose == 0:
        logger.setLevel(logging.ERROR)
    elif verbose == 1:
        logger.setLevel(logging.WARNING)
    elif verbose == 2:
        logger.setLevel(logging.INFO)
    elif verbose > 2:
        logger.setLevel(logging.DEBUG)
