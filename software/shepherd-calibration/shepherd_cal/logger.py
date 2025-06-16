import logging

log = logging.getLogger("shp.calTool")
log.setLevel(logging.INFO)


def activate_verbosity() -> None:
    log.setLevel(logging.DEBUG)
