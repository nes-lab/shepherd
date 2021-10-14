import gc
import time
import numpy as np
from pathlib import Path
import h5py
from typing import NoReturn


class LogWriter(object):

    compression = None  # "lzf"

    def __init__(
            self,
            store_path: Path,
            samples_per_buffer: int = 10_000,
            samplerate_sps: int = 100_000,
    ):
        self.store_path = store_path
        print(f"Storing data to   '{self.store_path}'")

        self.chunk_shape = True  # (samples_per_buffer,)
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
            compression=LogWriter.compression,
        )
        self.data_grp.create_dataset(
            "current",
            (self.data_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=self.compression,
        )
        self.data_grp.create_dataset(
            "voltage",
            (self.data_inc,),
            dtype="u4",
            maxshape=(None,),
            chunks=self.chunk_shape,
            compression=LogWriter.compression,
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
        runtime = round(self._h5file["data"]["time"].shape[0] / self.samplerate_sps, 1)
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
            db = {"voltage": self._h5file["data"]["voltage"][idx_start:idx_end],
                  "current": self._h5file["data"]["current"][idx_start:idx_end]}
            yield db


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
    duration = 200 * 60
    #benchmark_path = Path("/var/shepherd/recordings")
    benchmark_path = Path(".")
    file_rec = benchmark_path / "benchmark_rec.h5"
    file_emu = benchmark_path / "benchmark_emu.h5"

    print(h5py.version.info)
    print("ram is leaking during processing, not during generation")

    if not file_rec.exists():
        print("Starting Generating (hdf5 write)")
        record(output_path=file_rec, duration=duration)
        print(f"[GC] cleaned {gc.collect()} obj")

    print("Starting Processing (hdf5 read & write)")
    emulate(input_path=file_rec, output_path=file_emu)
    print(f"[GC] cleaned {gc.collect()} obj")
    
'''
Bug / script: 
- first file-creation with record() works fine, 200 min simulation with stable ~ 33 mb RAM usage 
- Ram is leaking during reading a previously created file in emulate()
    - up to ~ 180 mb ram for simulated 200 min duration
- tracemalloc and molly showed no leaking in the python-code itself

no influence:
- vlen-elements
- custom chunk-size
- compression

tested systems: 
Beaglebone, arm7
    - python 3.6, h5py 2.7.1, numpy 1.13.3
    - python 3.9.5, h5py 2.10.0, numpy 1.19.5
    - python 3.9.5, h5py 3.4.0, numpy 1.21.2
Lenovo W530, Intel x64 CPU
    - python 3.9.7, h5py 3.4.0, numpy 1.21.2
AMD Ryzen 5700
    - python 3.10, h5py 3.4.0, 
        
Output of h5py.version.info
h5py    3.4.0
HDF5    1.12.1
Python  3.9.7 (tags/v3.9.7:1016ef3, Aug 30 2021, 20:19:38) [MSC v.1929 64 bit (AMD64)]
sys.platform    win32
sys.maxsize     9223372036854775807
numpy   1.21.2
cython (built with) 0.29.24
numpy (built against) 1.19.3
HDF5 (built against) 1.12.1
    
'''
