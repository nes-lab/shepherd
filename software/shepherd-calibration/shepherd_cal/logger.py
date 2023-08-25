import logging

logger = logging.getLogger("shp.calTool")
logger.setLevel(logging.INFO)


def activate_verbose() -> None:
    logger.setLevel(logging.DEBUG)
