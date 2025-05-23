import threading
import time
from pathlib import Path
from types import TracebackType

import h5py
import serial
from shepherd_core import Compression
from shepherd_core.data_models.experiment.observer_features import UartLogging

from .h5_monitor_abc import Monitor
from .logger import log


class UARTMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
        uart: str = "/dev/ttyS1",
        config: UartLogging | None = None,
    ) -> None:
        super().__init__(target, compression, poll_interval=0.05)
        self.uart = uart
        self.config = config
        self.data.create_dataset(
            name="message",
            shape=(self.increment,),
            dtype=h5py.special_dtype(vlen=bytes),
            maxshape=(None,),
            chunks=True,
            compression=compression,
        )
        self.data["message"].attrs["description"] = "raw ascii-bytes"

        if config is None:
            return

        if (not isinstance(self.config.baudrate, int)) or (self.config.baudrate == 0):
            return

        if Path(self.uart).exists():
            log.info(
                "[%s] starts with '%s' @ %d baud, %d bit/byte, %.1f stopbit, %s parity",
                type(self).__name__,
                self.uart,
                self.config.baudrate,
                self.config.bytesize,
                self.config.stopbits,
                self.config.parity,
            )
            self.thread = threading.Thread(
                target=self.thread_fn,
                daemon=True,
                name="Shp.H5Mon.UART",
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
            self.thread.join(timeout=2 * self.poll_interval)
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
            with serial.Serial(
                self.uart,
                baudrate=self.config.baudrate,
                bytesize=self.config.bytesize,
                stopbits=self.config.stopbits,
                parity=self.config.parity,
                timeout=0,
            ) as uart:
                while not self.event.wait(self.poll_interval):  # rate limiter & exit
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
