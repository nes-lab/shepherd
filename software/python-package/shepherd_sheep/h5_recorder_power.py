import copy
import threading
from queue import Queue
from types import TracebackType

import h5py
import numpy as np
from shepherd_core.data_models.base.calibration import CalibrationEmulator as CalEmu
from shepherd_core.data_models.base.calibration import CalibrationSeries as CalSeries
from shepherd_core.data_models.content.enum_datatypes import Compression

from . import commons
from .h5_monitor_abc import Monitor
from .logger import log
from .shared_mem_iv_input import IVTrace
from .shared_mem_iv_output import SharedMemIVOutput


# TODO: can be another thread-fn in IVRecorder
class PowerRecorder(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        cal_data: CalSeries | CalEmu,
        compression: Compression | None = Compression.default,
        reduction_factor: int = 1,
    ) -> None:
        super().__init__(
            target,
            compression,
            poll_interval=0.66 * SharedMemIVOutput.DURATION_CHUNK_S,
            increment=10 * SharedMemIVOutput.N_SAMPLES_PER_CHUNK // reduction_factor,
        )
        if reduction_factor not in [1, 10, 100, 1000, 10000, 100_000]:
            raise ValueError("reduction-factor must be 10^n, n=[0..5]")
        self.reduction_factor: int = reduction_factor
        self.reduce: bool = self.reduction_factor != 1

        self.buffer_timeseries = (
            self.reduction_factor
            * commons.SAMPLE_INTERVAL_NS
            * np.arange(
                SharedMemIVOutput.N_SAMPLES_PER_CHUNK // self.reduction_factor,
            ).astype(np.uint64)
        )

        if isinstance(cal_data, CalEmu):
            self.cal_data = CalSeries.from_cal(cal_data)
        elif isinstance(cal_data, CalSeries):
            self.cal_data = cal_data
        else:
            raise TypeError("calibration must be CalibrationSeries or CalibrationEmulator")

        self.gain: float = 1e-9  # nW
        self.offset_V_raw = int(self.cal_data.voltage.offset / self.cal_data.voltage.gain)
        self.offset_C_raw = int(self.cal_data.current.offset / self.cal_data.current.gain)
        self.gain_P_nW = self.cal_data.voltage.gain * self.cal_data.current.gain / self.gain

        self.data.create_dataset(
            name="value",
            shape=(self.increment,),
            dtype="u4",
            maxshape=(None,),
            chunks=(self.increment,),
            compression=compression,
        )
        self.data["value"].attrs["unit"] = "W"
        self.data["value"].attrs["description"] = "Power [W] = value/nW * gain + (offset)"
        self.data["value"].attrs["gain"] = self.gain
        self.data["value"].attrs["offset"] = 0

        self.dropped_data = False
        self.queue_size = int(
            80e6 / (SharedMemIVOutput.SIZE_SAMPLE * SharedMemIVOutput.N_SAMPLES_PER_CHUNK)
        )  # MB
        self.queue = Queue(maxsize=self.queue_size)
        log.info("[%s] starts with size_queue = %d", type(self).__name__, self.queue_size)
        self.thread = threading.Thread(
            target=self.thread_fn_reduce if self.reduce else self.thread_fn,
            daemon=True,
            name="Shp.H5Rec.Power",
        )
        self.thread.start()

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.flush_queue()
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=20 * self.poll_interval)
            if self.thread.is_alive():
                log.warning(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        # py313 has shutdown for queue
        if self.dropped_data:
            log.error("[%s] dropped data due to backpressure", type(self).__name__)
        self.data["value"].resize((self.position,))
        super().__exit__()

    def write(self, data: IVTrace) -> None:
        if self.queue.full():
            self.dropped_data = True
            return  # drop package
        data_new = copy.deepcopy(data)
        self.queue.put(data_new)

    def thread_fn(self) -> None:
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                data = self.queue.get()
                len_add = len(data)
                """wanted:
                        self.cal_data.voltage.raw_to_si(data.voltage[:len_add]).astype(np.float32)
                        * self.cal_data.current.raw_to_si(data.current[:len_add]).astype(np.float32)
                        / self.gain
                Problem: upcast to float64 - which crashes the beaglebone
                """
                V_ = data.voltage[:len_add].clip(0, 2**18).astype(np.int64) + self.offset_V_raw
                C_ = data.current[:len_add].clip(0, 2**18).astype(np.int64) + self.offset_C_raw
                power = ((V_ * C_) * self.gain_P_nW).clip(0, 2**32).astype(np.uint32)

                # timestamps are automatically reduced
                if isinstance(data.timestamp_ns, int):
                    # This is currently not used
                    data.timestamp_ns = self.buffer_timeseries + data.timestamp_ns

                pos_end = self.position + len_add
                data_length = self.data["time"].shape[0]

                if pos_end >= data_length:
                    data_length += max(self.increment, pos_end - data_length)
                    self.data["time"].resize((data_length,))
                    self.data["value"].resize((data_length,))
                self.data["time"][self.position : pos_end] = data.timestamp_ns
                self.data["value"][self.position : pos_end] = power
                self.position = pos_end
        log.debug("[%s] thread ended itself", type(self).__name__)

    def thread_fn_reduce(self) -> None:
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                data = self.queue.get()
                len_add = len(data)
                if len_add < self.reduction_factor:  # is 1 when not used
                    return
                if len_add % self.reduction_factor != 0:
                    log.warning("Power-Tracer Input got odd size - some samples will be discarded")
                len_red = len_add // self.reduction_factor
                len_add = len_red * self.reduction_factor

                """wanted:
                        self.cal_data.voltage.raw_to_si(data.voltage[:len_add]).astype(np.float32)
                        * self.cal_data.current.raw_to_si(data.current[:len_add]).astype(np.float32)
                        / self.gain
                Problem: upcast to float64 - which crashes the beaglebone
                """
                V_ = data.voltage[:len_add].clip(0, 2**18).astype(np.int64) + self.offset_V_raw
                C_ = data.current[:len_add].clip(0, 2**18).astype(np.int64) + self.offset_C_raw
                power = ((V_ * C_) * self.gain_P_nW).clip(0, 2**32).astype(np.uint32)

                # timestamps are automatically reduced
                if isinstance(data.timestamp_ns, int):
                    # This is currently not used
                    data.timestamp_ns = self.buffer_timeseries[:len_red] + data.timestamp_ns
                elif isinstance(data.timestamp_ns, np.ndarray):
                    # benchmarked slices: [:] is as fast as [::1] on BBB
                    data.timestamp_ns = data.timestamp_ns[: len_add : self.reduction_factor]
                else:
                    raise TypeError("timestamp_ns must be int or np.ndarray")

                if self.reduce:
                    power = (
                        power.reshape(len_red, self.reduction_factor)
                        .mean(axis=1, dtype=np.uint64)
                        .astype(np.uint32)
                    )
                    len_add = len_red

                pos_end = self.position + len_add
                data_length = self.data["time"].shape[0]

                if pos_end >= data_length:
                    data_length += max(self.increment, pos_end - data_length)
                    self.data["time"].resize((data_length,))
                    self.data["value"].resize((data_length,))
                self.data["time"][self.position : pos_end] = data.timestamp_ns
                self.data["value"][self.position : pos_end] = power
                self.position = pos_end
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return

    def check_dataset(self, t_start: int, t_end: int) -> bool:
        self.flush_queue()
        had_error = False
        if self.position < 1:
            return had_error
        gain = self.data["time"].attrs["gain"]
        file_start = self.data["time"][0] * gain
        file_end = self.data["time"][self.position - 1] * gain
        if file_start > t_start:
            log.error("Recorder missed %.3f s IVTrace after start", file_start - t_start)
            had_error = True
        if file_end < t_end - max(
            1e-3, 2.0 * self.reduction_factor / commons.SAMPLE_RATE_DEFAULT_SPS
        ):
            log.error("Recorder missed ~ %.3f s IVTrace before end", t_end - file_end)
            had_error = True
        return had_error
