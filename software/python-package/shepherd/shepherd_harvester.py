import time
from typing import Optional

from . import sysfs_interface
from .calibration import CalibrationData
from .logger import logger
from .shepherd_io import ShepherdIO
from .virtual_harvester_config import T_vHrv
from .virtual_harvester_config import VirtualHarvesterConfig


class ShepherdHarvester(ShepherdIO):
    """API for recording a harvest with shepherd.

    Provides an easy-to-use, high-level interface for recording data with
    shepherd. Configures all hardware and initializes the communication
    with kernel module and PRUs.

    # TODO: DAC-Calibration would be nice to have, in case of active MPPT even both adc-cal

    Args:
        shepherd_mode (str): Should be 'harvester' to record harvesting data
        harvester: name, path or object to a virtual harvester setting

    """

    def __init__(
        self,
        shepherd_mode: str = "harvester",
        harvester: Optional[T_vHrv] = None,
        calibration: Optional[CalibrationData] = None,
    ):
        logger.debug("Recorder-Init in %s-mode", shepherd_mode)
        self.samplerate_sps = (
            10**9
            * sysfs_interface.get_samples_per_buffer()
            // sysfs_interface.get_buffer_period_ns()
        )
        self.harvester = VirtualHarvesterConfig(harvester, self.samplerate_sps)
        self.calibration = calibration
        super().__init__(shepherd_mode)

    def __enter__(self):
        super().__enter__()

        super().set_power_state_emulator(False)
        super().set_power_state_recorder(True)
        super().send_virtual_harvester_settings(self.harvester)
        super().send_calibration_settings(self.calibration)

        super().reinitialize_prus()  # needed for ADCs

        # Give the PRU empty buffers to begin with
        time.sleep(1)
        for i in range(self.n_buffers):
            time.sleep(
                0.1 * float(self.buffer_period_ns) / 1e9,
            )  # could be as low as ~ 10us
            self.return_buffer(i, True)

        return self

    def return_buffer(self, index: int, verbose: bool = False):
        """Returns a buffer to the PRU

        After reading the content of a buffer and potentially filling it with
        emulation data, we have to release the buffer to the PRU to avoid it
        running out of buffers.

        :param index: (int) Index of the buffer. 0 <= index < n_buffers
        :param verbose: chatter-prevention, performance-critical computation saver
        """
        super()._return_buffer(index)
        if verbose:
            logger.debug("Sent empty buffer #%s to PRU", index)
