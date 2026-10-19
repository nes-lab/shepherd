import threading
import time
from pathlib import Path
from types import TracebackType

import h5py
import serial
from shepherd_core.data_models.content.enum_datatypes import Compression
from shepherd_core.data_models.experiment.observer_features import UartLogging

from .h5_monitor_abc import Monitor
from .logger import log


class UARTMonitor(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        config: UartLogging,
        compression: Compression | None = Compression.default,
        uart: str = "/dev/ttyS1",
    ) -> None:
        super().__init__(target, compression, poll_interval=0.05)
        if self.poll_interval > (64_000 * 8 / 460_800) / 10:
            log.error(
                "[%s] poll interval is > 10x of expected flip buffer",
                type(self).__name__,
            )
            return
        """
        - tty flip buffer should be 64 kiB
        - at 460 kBaud (max of the interface) with full throughput that's roughly >= 1 s
        - to be safe the interval will be 1/10 of that
        """

        self.uart = uart
        self.config = config
        self.ds_message = self.data.create_dataset(
            name="message",
            shape=(self.ds_size,),
            dtype=h5py.special_dtype(vlen=bytes),
            maxshape=(None,),
            chunks=(self.chunk_size,),
        )
        self.ds_message.attrs["description"] = "raw ascii-bytes"

        if not isinstance(self.config, UartLogging):
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
        self.shutdown_thread()
        self.ds_message.resize((self.position,))
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
                while not self.event.is_set():
                    if uart.in_waiting > 0:
                        # hdf5 can embed raw bytes, but can't handle nullbytes
                        output = uart.read(uart.in_waiting).replace(b"\x00", b"")
                        if len(output) > 0:
                            if self.position >= self.ds_size:
                                self.ds_size += self.increment_size
                                self.ds_time.resize((self.ds_size,))
                                self.ds_message.resize((self.ds_size,))
                            self.ds_time[self.position] = int(time.time() * 1e9)
                            self.ds_message[self.position] = output
                            self.position += 1
                    self.event.wait(self.poll_interval)

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
                self.config.baudrate,
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

    def check_status(self) -> None:
        return

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        # leave as is
