import threading
import time
from pathlib import Path
from types import TracebackType

import h5py
import serial
from shepherd_core import Compression

from .logger import log
from .monitor_abc import Monitor


class UARTMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
        uart: str = "/dev/ttyS1",
        baudrate: int | None = None,
    ) -> None:
        super().__init__(target, compression, poll_intervall=0.05)
        self.uart = uart
        self.baudrate = baudrate
        self.data.create_dataset(
            "message",
            (self.increment,),
            dtype=h5py.special_dtype(vlen=bytes),
            maxshape=(None,),
            chunks=True,
            compression=compression,
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
            self.thread = threading.Thread(
                target=self.thread_fn, daemon=True, name="UARTMon"
            )
            self.thread.start()
        else:
            log.error(
                "[%s] will not start - '%s' is unavailable",
                type(self).__name__,
                self.uart,
            )

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=2 * self.poll_intervall)
            if self.thread.is_alive():
                log.error(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        self.data["message"].resize((self.position,))
        super().__exit__()

    def thread_fn(self) -> None:
        # - uart is bytes-type -> storing in hdf5 is hard,
        #   tried 'S' and opaque-type -> failed with errors
        # - converting is producing ValueError on certain chars,
        #   errors="backslashreplace" does not help
        # https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.to_bytes
        # TODO: is there a way to signal backpressure?
        try:
            # open serial as non-exclusive
            with serial.Serial(self.uart, self.baudrate, timeout=0) as uart:
                while not self.event.wait(self.poll_intervall):  # rate limiter & exit
                    if uart.in_waiting > 0:
                        # hdf5 can embed raw bytes, but can't handle nullbytes
                        output = uart.read(uart.in_waiting).replace(b"\x00", b"")
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

        except RuntimeError:
            log.error("[%s] HDF5-File unavailable - will stop", type(self).__name__)
        except ValueError as e:
            log.error(
                "[%s] PySerial ValueError '%s' - "
                "couldn't configure serial-port '%s' "
                "with baudrate=%d -> prevents logging",
                type(self).__name__,
                e,
                self.uart,
                self.baudrate,
            )
        except serial.SerialException as e:
            log.error(
                "[%s] pySerial SerialException '%s - "
                "Couldn't open Serial-Port '%s' to target -> prevents logging",
                type(self).__name__,
                e,
                self.uart,
            )
        log.debug("[%s] thread ended itself", type(self).__name__)
