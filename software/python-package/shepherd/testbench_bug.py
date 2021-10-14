import gc
import time
import numpy as np
from pathlib import Path
import h5py
from typing import NoReturn


def record(output_path: Path, duration: int):
    length = 10_000
    with LogWriter(output_path) as drain:
        for _ in range(duration * 10):
            buf = {"voltage": np.zeros(length, dtype="u4"),
                   "current": np.zeros(length, dtype="u4"),
                   "timestamp": int(time.time() * 10 ** 9),}
            drain.write_buffer(buf)


def emulate(input_path: Path, output_path: Path):
    with LogReader(input_path) as source, LogWriter(output_path) as drain:
        for data_buf in source.read_buffers():
            buf = {"voltage": data_buf["voltage"],
                   "current": data_buf["current"],  # np.zeros(length, dtype="u4"),
                   "timestamp": int(time.time() * 10 ** 9),}
            drain.write_buffer(buf)


if __name__ == "__main__":
    duration = 25 * 60
    benchmark_path = Path("/var/shepherd/recordings")
    file_rec = benchmark_path / "db_voltage04h.h5" #"benchmark_rec.h5"
    file_emu = benchmark_path / "benchmark_emu.h5"

    print(h5py.version.info)
    print("ram is leaking during processing, not during generation -> only difference: h5py lzf-reading")

    print("Starting Generating")
    #record(output_path=file_rec, duration=duration)
    print(f"cleaned {gc.collect()} obj")

    print("Starting Processing")
    emulate(input_path=file_rec, output_path=file_emu)
    print(f"cleaned {gc.collect()} obj")


class LogWriter(object):

    compression_algo = "lzf"

    def __init__(
            self,
            store_path: Path,
            samples_per_buffer: int = 10_000,
            samplerate_sps: int = 100_000,
    ):
        self.store_path = store_path
        print(f"Storing data to   '{self.store_path}'")

        self.chunk_shape = (samples_per_buffer,)
        self.samplerate_sps = int(samplerate_sps)
        self.sample_interval_ns = int(10 ** 9 // samplerate_sps)
        self.buffer_timeseries = self.sample_interval_ns * np.arange(samples_per_buffer).astype("u8")

        inc_duration = int(10)
        inc_length = int(inc_duration * samplerate_sps)
        self.data_pos = 0
        self.data_inc = inc_length

    def __enter__(self):

        self._h5file = h5py.File(self.store_path, "w")

        # Store voltage and current samples in the data group, both are stored as 4 Byte unsigned int
        self.data_grp = self._h5file.create_group("data")
        self.data_grp.create_dataset(
            "time",
            (self.data_inc,),
            dtype="u8",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=LogWriter.compression_algo,
        )
        self.data_grp.create_dataset(
            "current",
            (self.data_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=self.compression_algo,
        )
        self.data_grp.create_dataset(
            "voltage",
            (self.data_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=LogWriter.compression_algo,
        )

        return self

    def __exit__(self, *exc):
        self.data_grp["time"].resize((self.data_pos,))
        self.data_grp["voltage"].resize((self.data_pos,))
        self.data_grp["current"].resize((self.data_pos,))

        runtime = round(self.data_grp['time'].shape[0] // self.samplerate_sps, 1)
        print(f"[LogWriter] flushing hdf5 file ({runtime} s data)")
        self._h5file.flush()
        print("[LogWriter] closing  hdf5 file")
        self._h5file.close()

    def write_buffer(self, buffer) -> NoReturn:
        data_end_pos = self.data_pos + len(buffer["voltage"])
        data_length = self.data_grp["time"].shape[0]
        if data_end_pos >= data_length:
            data_length += self.data_inc
            self.data_grp["time"].resize((data_length,))
            self.data_grp["voltage"].resize((data_length,))
            self.data_grp["current"].resize((data_length,))

        self.data_grp["voltage"][self.data_pos:data_end_pos] = buffer["voltage"]
        self.data_grp["current"][self.data_pos:data_end_pos] = buffer["current"]
        self.data_grp["time"][self.data_pos:data_end_pos] = (
                    self.buffer_timeseries + buffer["timestamp"]
            )
        self.data_pos = data_end_pos


class LogReader(object):
    def __init__(self,
                 store_path: Path,
                 samples_per_buffer: int = 10_000,
                 samplerate_sps: int = 100_000):
        self.store_path = store_path
        self.samples_per_buffer = samples_per_buffer
        self.samplerate_sps = samplerate_sps

    def __enter__(self):
        self._h5file = h5py.File(self.store_path, "r")
        self.ds_voltage = self._h5file["data"]["voltage"]
        self.ds_current = self._h5file["data"]["current"]
        runtime = round(self.ds_voltage.shape[0] / self.samplerate_sps, 1)
        print(f"Reading data from '{self.store_path}', contains {runtime} s")
        return self

    def __exit__(self, *exc):
        self._h5file.close()

    def read_buffers(self, start: int = 0, end: int = None, verbose: bool = False):
        if end is None:
            end = int(
                self._h5file["data"]["time"].shape[0] / self.samples_per_buffer
            )
        print(f"Reading blocks from {start} to {end} from source-file")

        for i in range(start, end):
            idx_start = i * self.samples_per_buffer
            idx_end = idx_start + self.samples_per_buffer
            db = {"voltage": self.ds_voltage[idx_start:idx_end],
                  "current": self.ds_current[idx_start:idx_end]}
            yield db
