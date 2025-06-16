import logging

import chromalog

chromalog.basicConfig(format="%(message)s")
log: logging.Logger = logging.getLogger("Receiver")
log.setLevel(logging.INFO)
log.addHandler(logging.NullHandler())


def activate_verbosity() -> None:
    log.setLevel(logging.DEBUG)
