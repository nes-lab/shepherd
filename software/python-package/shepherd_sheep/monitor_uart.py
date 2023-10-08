import threading
import time
from pathlib import Path
from typing import Optional

import h5py
import serial
from shepherd_core import Compression

from .logger import log
from .monitor_abc import Monitor


class UARTMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Optional[Compression] = Compression.default,
        uart: str = "/dev/ttyS1",
        baudrate: Optional[int] = None,
    ):
        super().__init__(target, compression, poll_intervall=0.01)
        self.uart = uart
        self.baudrate = baudrate
        self.data.create_dataset(
            "message",
            (self.increment,),
            dtype=h5py.special_dtype(vlen=bytes),
            maxshape=(None,),
            chunks=True,
        )
        self.data["message"].attrs["description"] = "raw ascii-bytes"

        if (not isinstance(self.baudrate, int)) or (self.baudrate == 0):
            return

        if Path(self.uart).exists():
            log.info(
                "[%s] starts with '%s' @ %d baud",
                type(self).__name__,
                self.uart,
                self.baudrate,
            )
            self.thread = threading.Thread(target=self.thread_fn, daemon=True)
            self.thread.start()
        else:
            log.error(
                "[%s] will not start - '%s' is unavailable",
                type(self).__name__,
                self.uart,
            )

    def __exit__(self, *exc):  # type: ignore
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=self.poll_intervall)
            self.thread = None
        self.data["message"].resize((self.position,))
        super().__exit__()

    def thread_fn(self) -> None:
        # - uart is bytes-type -> storing in hdf5 is hard,
        #   tried 'S' and opaque-type -> failed with errors
        # - converting is producing ValueError on certain chars,
        #   errors="backslashreplace" does not help
        # TODO: eval https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.to_bytes
        try:
            # open serial as non-exclusive
            with serial.Serial(self.uart, self.baudrate, timeout=0) as uart:
                while not self.event.is_set():
                    if uart.in_waiting > 0:
                        # hdf5 can embed raw bytes, but can't handle nullbytes
                        output = uart.read(uart.in_waiting).replace(b"\x00", b"")
                        if self.event.is_set():
                            # needed because uart.read is blocking
                            break
                        if len(output) > 0:
                            data_length = self.data["time"].shape[0]
                            if self.position >= data_length:
                                data_length += self.increment
                                self.data["time"].resize((data_length,))
                                self.data["message"].resize((data_length,))
                            self.data["time"][self.position] = int(
                                time.time() * 1e9,
                            )
                            self.data["message"][self.position] = output
                            self.position += 1
                    self.event.wait(self.poll_intervall)  # rate limiter
        except ValueError as e:
            log.error(  # noqa: G200
                "[%s] PySerial ValueError '%s' - "
                "couldn't configure serial-port '%s' "
                "with baudrate=%d -> prevents logging",
                type(self).__name__,
                e,
                self.uart,
                self.baudrate,
            )
        except serial.SerialException as e:
            log.error(  # noqa: G200
                "[%s] pySerial SerialException '%s - "
                "Couldn't open Serial-Port '%s' to target -> prevents logging",
                type(self).__name__,
                e,
                self.uart,
            )
        log.debug("[%s] thread ended itself", type(self).__name__)
