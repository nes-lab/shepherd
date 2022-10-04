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

from .sheep_control import check_sheep
from .sheep_control import configure_sheep
from .sheep_control import find_consensus_time
from .sheep_control import logger
from .sheep_control import poweroff_sheep
from .sheep_control import start_sheep
from .sheep_control import stop_sheep

__version__ = "0.4.2"

__all__ = [
    "logger",
    "find_consensus_time",
    "start_sheep",
    "check_sheep",
    "stop_sheep",
    "configure_sheep",
    "poweroff_sheep",
]
