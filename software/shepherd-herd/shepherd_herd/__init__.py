"""
shepherd_herd
~~~~~
click-based command line utility for controlling a group of shepherd nodes
remotely through ssh. Provides commands for starting/stopping harvester and
emulator, retrieving recordings to the local machine and flashing firmware
images to target sensor nodes.

"""

from .herd import Herd
from .logger import get_verbosity
from .logger import logger
from .logger import set_verbosity

__version__ = "0.8.0"

__all__ = [
    "Herd",
    "logger",
    "set_verbosity",
    "logger",
    "get_verbosity",
]
