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
            increment=10 * SharedMemIVOutput.N_SAMPLES_PER_CHUNK // reduction_factor,
        )
        if reduction_factor not in [1, 10, 100, 1000, 10000, 100_000]:
            raise ValueError("reduction-factor must be 10^n, n=[0..5]")
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

        self.dropped_data = False
        self.queue_size = int(
            80e6 / (SharedMemIVOutput.SIZE_SAMPLE * SharedMemIVOutput.N_SAMPLES_PER_CHUNK)
        )  # MB
        self.queue = Queue(maxsize=self.queue_size)
        log.info("[%s] buffered with queue-size = %d", type(self).__name__, self.queue_size)
        self.thread = threading.Thread(
            target=self.thread_fn_reduce if self.reduce else self.thread_fn,
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
        self.finalize_write()
        # py313 has shutdown for queue
        if self.dropped_data:
            log.error("[%s] dropped data due to backpressure", type(self).__name__)
        self.data["voltage"].resize((self.position,))
        self.data["current"].resize((self.position,))
        super().__exit__()

    def finalize_write(self) -> int:
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=20 * self.poll_interval)
            if self.thread.is_alive():
                log.warning(
                    "[%s] thread failed to end itself - will delete that instance",
                    type(self).__name__,
                )
            self.thread = None
        return self.position

    def write(self, data: IVTrace) -> None:
        if self.queue.full():
            self.dropped_data = True
            return  # drop package
        data_new = copy.deepcopy(data)
        self.queue.put(data_new)

    def thread_fn(self) -> None:  # optimized for normal operation
        while not self.event.is_set():
            if self.queue.empty():
                self.event.wait(self.poll_interval)  # rate limiter
            else:
                data = self.queue.get()
                len_add = len(data)
                if len_add < 1:
                    return
                if isinstance(data.timestamp_ns, int):
                    data.timestamp_ns = self.buffer_timeseries + data.timestamp_ns
                pos_end = self.position + len_add
                data_length = self.data["voltage"].shape[0]
                if pos_end >= data_length:
                    data_length += self.increment
                    # TODO: faster with direct naming? i.e. self.ds_time
                    self.data["voltage"].resize((data_length,))
                    self.data["current"].resize((data_length,))
                    self.data["time"].resize((data_length,))

                self.data["voltage"][self.position : pos_end] = data.voltage
                self.data["current"][self.position : pos_end] = data.current
                self.data["time"][self.position : pos_end] = data.timestamp_ns
                self.position = pos_end
        # TODO: catch OSError - "Failed to write data to HDF5-File - will STOP! error = %s",
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
                len_red = len(data) // self.reduction_factor
                len_add = len_red * self.reduction_factor

                # timestamps are automatically reduced
                if isinstance(data.timestamp_ns, int):
                    data.timestamp_ns = self.buffer_timeseries[:len_red] + data.timestamp_ns
                elif isinstance(data.timestamp_ns, np.ndarray):
                    # benchmarked slices: [:] is as fast as [::1] on BBB
                    data.timestamp_ns = data.timestamp_ns[: len_add : self.reduction_factor]
                else:
                    raise TypeError("timestamp_ns must be int or np.ndarray")

                if self.reduce:  # aka resampling via binning
                    # Note: input is u18, max reduction is 10k (u14), so u32 should be fine
                    data.voltage = (
                        data.voltage[:len_add]
                        .reshape(len_red, self.reduction_factor)
                        .mean(axis=1, dtype=np.uint64)
                        .clip(0, 2**32)
                        .astype(np.uint32)
                    )
                    data.current = (
                        data.current[:len_add]
                        .reshape(len_red, self.reduction_factor)
                        .mean(axis=1, dtype=np.uint64)
                        .clip(0, 2**32)
                        .astype(np.uint32)
                    )
                    len_add = len_red

                # add to file
                data_end_pos = self.position + len_add
                data_length_h5 = self.data["voltage"].shape[0]
                if data_end_pos >= data_length_h5:
                    data_length_h5 += self.increment
                    self.data["voltage"].resize((data_length_h5,))
                    self.data["current"].resize((data_length_h5,))
                    self.data["time"].resize((data_length_h5,))

                self.data["voltage"][self.position : data_end_pos] = data.voltage
                self.data["current"][self.position : data_end_pos] = data.current
                self.data["time"][self.position : data_end_pos] = data.timestamp_ns
                self.position = data_end_pos
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
