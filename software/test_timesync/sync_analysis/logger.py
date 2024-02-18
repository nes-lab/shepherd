import logging

import chromalog

chromalog.basicConfig(format="%(message)s")
logger: logging.Logger = logging.getLogger("Receiver")
logger.setLevel(logging.INFO)
logger.addHandler(logging.NullHandler())
