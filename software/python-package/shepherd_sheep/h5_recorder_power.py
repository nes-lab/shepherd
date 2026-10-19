import copy
import threading
from queue import Queue
from types import TracebackType

import h5py
import numpy as np
from shepherd_core.data_models.base.calibration import CalibrationEmulator as CalEmu
from shepherd_core.data_models.base.calibration import CalibrationSeries as CalSeries
from shepherd_core.data_models.content.enum_datatypes import Compression
from shepherd_core.data_models.experiment.observer_features import samplerates_supported

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
            increment_factor=20,
            chunk_size=10_000,
            # NOTE: was SharedMemIVOutput.N_SAMPLES_PER_CHUNK, but hope to lower large nw-bursts
        )
        reductions_supported = [
            commons.SAMPLE_RATE_DEFAULT_SPS // rate for rate in samplerates_supported
        ]
        if reduction_factor not in reductions_supported:
            raise ValueError("reduction-factor must be 10^n, n=[0..4]")
        self.reduction_factor: int = reduction_factor
        self.reduce: bool = self.reduction_factor != 1
        self.debug: bool = False

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

        self.use_float: bool = True
        self.gain: float = 1e-9  # nW
        self.offset_V_raw = int(self.cal_data.voltage.offset / self.cal_data.voltage.gain)
        self.offset_C_raw = int(self.cal_data.current.offset / self.cal_data.current.gain)
        self.gain_P_nW = self.cal_data.voltage.gain * self.cal_data.current.gain / self.gain

        if self.reduce:
            self.transform_data = (
                self.transform_data_float_reduce
                if self.use_float
                else self.transform_data_int_reduce
            )
        else:
            self.transform_data = (
                self.transform_data_float_full if self.use_float else self.transform_data_int_full
            )

        self.ds_value = self.data.create_dataset(
            name="value",
            shape=(self.ds_size,),
            dtype="u4",
            maxshape=(None,),
            chunks=(self.chunk_size,),
            compression=compression,
            shuffle=True,
        )
        self.ds_value.attrs["unit"] = "W"
        self.ds_value.attrs["description"] = "Power [W] = value/nW * gain + (offset)"
        self.ds_value.attrs["gain"] = self.gain
        self.ds_value.attrs["offset"] = 0

        self.dropped_data = False
        self.queue_size = int(
            80e6 / (SharedMemIVOutput.SIZE_SAMPLE * SharedMemIVOutput.N_SAMPLES_PER_CHUNK)
        )  # MB
        self.queue = Queue(maxsize=self.queue_size)
        log.debug("[%s] starts with size_queue = %d", type(self).__name__, self.queue_size)
        self.thread = threading.Thread(
            target=self.thread_fn,
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
        self.shutdown_thread()
        # py313 has shutdown for queue
        if self.dropped_data:
            log.error("[%s] dropped data due to backpressure", type(self).__name__)
        self.ds_value.resize((self.position,))
        super().__exit__()

    def write(self, data: IVTrace) -> None:
        if self.queue.full():
            self.dropped_data = True
            return  # drop package
        if len(data) < 1:
            return
        data_new = copy.deepcopy(data)
        self.queue.put(data_new)

    def transform_data_float_full(self, data: IVTrace) -> tuple[np.ndarray, np.ndarray]:
        """Faster, BUT upcast to float64 crashed the beaglebone kernel 4.19."""
        len_data = len(data)
        ds_power = (
            (
                self.cal_data.voltage.raw_to_si(data.ds_voltage[:len_data])
                * self.cal_data.current.raw_to_si(data.ds_current[:len_data])
                / self.gain
            )
            .clip(0, 2**32 - 1)
            .astype(np.uint32)
        )
        ds_time = (
            self.buffer_timeseries[:len_data] + data.ds_time
            if isinstance(data.ds_time, int)
            else data.ds_time[:len_data]
        )
        return (ds_time, ds_power)

    def transform_data_int_full(self, data: IVTrace) -> tuple[np.ndarray, np.ndarray]:
        """Faster, BUT upcast to float64 crashed the beaglebone kernel 4.19."""
        len_data = len(data)
        V_ = data.ds_voltage[:len_data].clip(0, 2**18 - 1).astype(np.int64) + self.offset_V_raw
        C_ = data.ds_current[:len_data].clip(0, 2**18 - 1).astype(np.int64) + self.offset_C_raw
        ds_power = ((V_ * C_) * self.gain_P_nW).clip(0, 2**32 - 1).astype(np.uint32)
        ds_time = (
            self.buffer_timeseries[:len_data] + data.ds_time
            if isinstance(data.ds_time, int)
            else data.ds_time[:len_data]
        )
        return (ds_time, ds_power)

    def transform_data_float_reduce(self, data: IVTrace) -> tuple[np.ndarray, np.ndarray]:
        len_redu = len(data) // self.reduction_factor
        len_data = len_redu * self.reduction_factor
        if self.debug:
            if len_data < self.reduction_factor:  # is 1 when not used
                raise ValueError("Power-Tracer Input is smaller than reduction factor")
            if len_data % self.reduction_factor != 0:
                raise ValueError("Power-Tracer Input is not multiple of reduction factor")
        ds_power = (
            (
                self.cal_data.voltage.raw_to_si(data.ds_voltage[:len_data])
                * self.cal_data.current.raw_to_si(data.ds_current[:len_data])
                / self.gain
            )
            .reshape(len_redu, self.reduction_factor)
            .mean(axis=1)
            .clip(0, 2**32 - 1)
            .astype(np.uint32)
        )
        if isinstance(data.ds_time, int):
            ds_time = self.buffer_timeseries[:len_redu] + data.ds_time
        else:
            # benchmarked slices: [:] is as fast as [::1] on BBB
            ds_time = data.ds_time[: len_data : self.reduction_factor]
        return (ds_time, ds_power)

    def transform_data_int_reduce(self, data: IVTrace) -> tuple[np.ndarray, np.ndarray]:
        len_redu = len(data) // self.reduction_factor
        len_data = len_redu * self.reduction_factor
        if self.debug:
            if len_data < self.reduction_factor:  # is 1 when not used
                raise ValueError("Power-Tracer Input is smaller than reduction factor")
            if len_data % self.reduction_factor != 0:
                raise ValueError("Power-Tracer Input is not multiple of reduction factor")
        V_ = data.ds_voltage[:len_data].clip(0, 2**18 - 1).astype(np.int64) + self.offset_V_raw
        C_ = data.ds_current[:len_data].clip(0, 2**18 - 1).astype(np.int64) + self.offset_C_raw
        ds_power = ((V_ * C_) * self.gain_P_nW).clip(0, 2**32 - 1).astype(np.uint32)
        ds_power = (
            ds_power.reshape(len_redu, self.reduction_factor)
            .mean(axis=1, dtype=np.uint64)
            .astype(np.uint32)
        )
        if isinstance(data.ds_time, int):
            ds_time = self.buffer_timeseries[:len_redu] + data.ds_time
        else:
            # benchmarked slices: [:] is as fast as [::1] on BBB
            ds_time = data.ds_time[: len_data : self.reduction_factor]
        return (ds_time, ds_power)

    def thread_fn(self) -> None:
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                ds_time, ds_pwr = self.transform_data(self.queue.get())
                pos_end = self.position + len(ds_time)
                if pos_end >= self.ds_size:
                    self.ds_size += self.increment_size
                    self.ds_time.resize((self.ds_size,))
                    self.ds_value.resize((self.ds_size,))
                self.ds_time[self.position : pos_end] = ds_time
                self.ds_value[self.position : pos_end] = ds_pwr
                self.position = pos_end
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return

    def check_dataset(self, t_start: int, t_end: int) -> bool:
        self.flush_queue()
        had_error = False
        if self.position < 1:
            return had_error
        gain = self.ds_time.attrs["gain"]
        file_start = self.ds_time[0] * gain
        file_end = self.ds_time[self.position - 1] * gain
        if file_start > t_start:
            log.error("Recorder missed %.3f s IVTrace after start", file_start - t_start)
            had_error = True
        if file_end < t_end - max(
            1e-3, 2.0 * self.reduction_factor / commons.SAMPLE_RATE_DEFAULT_SPS
        ):
            log.error("Recorder missed ~ %.3f s IVTrace before end", t_end - file_end)
            had_error = True
        return had_error

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        runtime_addition = 0
        datarate_sps = commons.SAMPLE_RATE_DEFAULT_SPS // self.reduction_factor
        self.ds_size = max(
            len(self.ds_time),
            self.increment_size,
            round(datarate_sps * (runtime_addition + value_s)),
        )
        self.ds_time.resize((self.ds_size,))
        self.ds_value.resize((self.ds_size,))
