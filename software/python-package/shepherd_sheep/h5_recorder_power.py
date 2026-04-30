from types import TracebackType

import h5py
import numpy as np
from shepherd_core.data_models.base.calibration import CalibrationEmulator as CalEmu
from shepherd_core.data_models.base.calibration import CalibrationSeries as CalSeries
from shepherd_core.data_models.content.enum_datatypes import Compression

from .commons import SAMPLE_INTERVAL_NS
from .h5_monitor_abc import Monitor
from .logger import log
from .shared_mem_iv_input import IVTrace
from .shared_mem_iv_output import SharedMemIVOutput


class PowerRecorder(Monitor):
    RATES_SUPPORTED = (10, 100, 1_000, 100_000)

    def __init__(
        self,
        data_rate: int,
        cal_data: CalSeries | CalEmu,
        target: h5py.Group,
        compression: Compression | None = Compression.default,
    ) -> None:
        super().__init__(
            target, compression, poll_interval=0, increment=SharedMemIVOutput.N_SAMPLES_PER_CHUNK
        )
        self.samplerate_sps: int = 10**9 // SAMPLE_INTERVAL_NS
        if data_rate not in self.RATES_SUPPORTED:
            raise ValueError(
                "Data-rate for Power must be in [Hz, Samples-per-second]: %s",
                self.RATES_SUPPORTED,
            )
        self.data_rate = data_rate
        self.reduction_factor: int = self.samplerate_sps // self.data_rate
        self.reduce: bool = self.data_rate != self.samplerate_sps

        self.buffer_timeseries = (
            self.reduction_factor
            * SAMPLE_INTERVAL_NS
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

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        self.data["value"].resize((self.position,))
        super().__exit__()

    def write(self, data: IVTrace) -> None:
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

    def thread_fn(self) -> None:
        raise NotImplementedError("A non-atomic monitor-thread corrupts shared-memory-access")
