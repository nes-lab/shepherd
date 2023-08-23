"""
shepherd_herd
~~~~~
click-based command line utility for controlling a group of shepherd nodes
remotely through ssh. Provides commands for starting/stopping harvester and
emulator, retrieving recordings to the local machine and flashing firmware
images to target sensor nodes.

:copyright: (c) 2019 Networked Embedded Systems Lab, TU Dresden.
:license: MIT, see LICENSE for more details.
"""
from .herd import Herd
from .herd import logger
from .herd import set_verbose_level

__version__ = "0.4.5"

__all__ = [
    "Herd",
    "logger",
    "set_verbose_level",
]
