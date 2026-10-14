import copy
import threading
from queue import Queue
from types import TracebackType

import h5py
import numpy as np

from . import commons
from .h5_monitor_abc import Monitor
from .logger import log
from .shared_mem_iv_input import IVTrace
from .shared_mem_iv_output import SharedMemIVOutput


class IVRecorder(Monitor):
    def __init__(
        self,
        target: h5py.Group,
        reduction_factor: int = 1,
    ) -> None:
        super().__init__(
            target,
            poll_interval=0.66 * SharedMemIVOutput.DURATION_CHUNK_S,
            chunk_size=SharedMemIVOutput.N_SAMPLES_PER_CHUNK,
            # NOTE: was 10 x CHUNK/REDUCTION_FACTOR, BUT performance was worse!
        )
        if reduction_factor not in [1, 10, 100, 1_000, 10_000]:
            raise ValueError("reduction-factor must be 10^n, n=[0..4]")
        # this monitor won't create its own datasets
        self.reduction_factor: int = reduction_factor
        self.reduce: bool = self.reduction_factor != 1
        self.buffer_timeseries = (
            self.reduction_factor
            * commons.SAMPLE_INTERVAL_NS
            * np.arange(
                SharedMemIVOutput.N_SAMPLES_PER_CHUNK // self.reduction_factor,
            ).astype(np.uint64)
        )
        self.debug: bool = False
        self.transform_data = (
            self.transform_data_reduce if self.reduce else self.transform_data_full
        )

        self.dropped_data = False
        self.queue_size = int(
            80e6 / (SharedMemIVOutput.SIZE_SAMPLE * SharedMemIVOutput.N_SAMPLES_PER_CHUNK)
        )  # MB
        self.queue = Queue(maxsize=self.queue_size)
        log.debug("[%s] buffered with queue-size = %d", type(self).__name__, self.queue_size)
        self.thread = threading.Thread(
            target=self.thread_fn,
            daemon=True,
            name="Shp.H5Rec.IV",
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
        self.data["voltage"].resize((self.position,))
        self.data["current"].resize((self.position,))
        super().__exit__()

    def write(self, data: IVTrace) -> None:
        if self.queue.full():
            self.dropped_data = True
            return  # drop package
        if len(data) < 1:
            return
        data_new = copy.deepcopy(data)
        self.queue.put(data_new)

    def transform_data_full(self, data: IVTrace) -> IVTrace:
        len_data = len(data)
        data.ds_voltage = data.ds_voltage[:len_data]
        data.ds_current = data.ds_current[:len_data]
        data.ds_time = (
            self.buffer_timeseries[:len_data] + data.ds_time
            if isinstance(data.ds_time, int)
            else data.ds_time[:len_data]
        )
        return data

    def transform_data_reduce(self, data: IVTrace) -> IVTrace:
        len_redu = len(data) // self.reduction_factor
        len_data = len_redu * self.reduction_factor
        if self.debug:
            if len_data < self.reduction_factor:  # is 1 when not used
                raise ValueError("IV-Tracer Input is smaller than reduction factor")
            if len_data % self.reduction_factor != 0:
                raise ValueError("IV-Tracer Input is not multiple of reduction factor")
        # reduce, aka resampling via binning
        # Note: input is u18, max reduction is 10k (u14), so u32 should be fine
        data.ds_voltage = (
            data.ds_voltage[:len_data]
            .reshape(len_redu, self.reduction_factor)
            .mean(axis=1, dtype=np.uint64)
            .clip(0, 2**32 - 1)
            .astype(np.uint32)
        )
        data.ds_current = (
            data.ds_current[:len_data]
            .reshape(len_redu, self.reduction_factor)
            .mean(axis=1, dtype=np.uint64)
            .clip(0, 2**32 - 1)
            .astype(np.uint32)
        )
        # timestamps are automatically reduced
        if isinstance(data.ds_time, int):
            data.ds_time = self.buffer_timeseries[:len_redu] + data.ds_time
        else:
            # benchmarked slices: [:] is as fast as [::1] on BBB
            data.ds_time = data.ds_time[: len_data : self.reduction_factor]
        return data

    def thread_fn(self) -> None:  # optimized for normal operation
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                data = self.transform_data(self.queue.get())
                pos_end = self.position + len(data)
                data_length = len(self.data["voltage"])  # faster .shape[0]
                if pos_end >= data_length:
                    data_length += self.increment_size
                    # TODO: faster with direct naming? i.e. self.ds_time
                    self.data["voltage"].resize((data_length,))
                    self.data["current"].resize((data_length,))
                    self.data["time"].resize((data_length,))

                self.data["voltage"][self.position : pos_end] = data.ds_voltage
                self.data["current"][self.position : pos_end] = data.ds_current
                self.data["time"][self.position : pos_end] = data.ds_time
                self.position = pos_end
        # TODO: catch OSError - "Failed to write data to HDF5-File - will STOP! error = %s",
        log.debug("[%s] thread ended itself", type(self).__name__)

    def check_status(self) -> None:
        return

    def check_dataset(self, t_start: int, t_end: int) -> bool:
        # TODO: bring this feature to the other recorders?
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

    def preshape_by_runtime(self, value_s: float) -> None:
        """Reshape some datasets with predictable length."""
        runtime_addition = 0
        datarate_sps = commons.SAMPLE_RATE_DEFAULT_SPS // self.reduction_factor
        data_length = max(
            len(self.data["time"]),
            self.increment_size,
            round(datarate_sps * (runtime_addition + value_s)),
        )
        self.data["time"].resize((data_length,))
        self.data["voltage"].resize((data_length,))
        self.data["current"].resize((data_length,))
