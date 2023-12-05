"""
Worst Case (RNG) test
- Variables: compression, randomness of data
- old: current design
- new: eval h5py.directRead()/Write() feature

BBB

    RUN with duration 60 s, compression lzf, random False
        Old F2RAM = 8.26 s, RAM2F = 25.749 s
        New F2RAM = 8.622 s, RAM2F = 15.615 s, RAM2Fts = 33.543
        Size f_in = 51.24 MB,  f_old = 51.252 MB,  f_new = 21.729 MB,  f_nts = 51.252 MB
    RUN with duration 60 s, compression 1, random False
        Old F2RAM = 8.602 s, RAM2F = 37.842 s
        New F2RAM = 10.632 s, RAM2F = 19.224 s, RAM2Fts = 41.972
        Size f_in = 25.203 MB,  f_old = 25.205 MB,  f_new = 9.859 MB,  f_nts = 25.205 MB
    RUN with duration 60 s, compression None, random False
        Old F2RAM = 3.863 s, RAM2F = 19.868 s
        New F2RAM = 8.583 s, RAM2F = 9.899 s, RAM2Fts = 24.901
        Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
    RUN with duration 60 s, compression lzf, random True
        Old F2RAM = 7.468 s, RAM2F = 39.102 s
        New F2RAM = 4.053 s, RAM2F = 28.189 s, RAM2Fts = 45.096
        Size f_in = 75.344 MB,  f_old = 75.356 MB,  f_new = 45.832 MB,  f_nts = 75.356 MB
    RUN with duration 60 s, compression 1, random True
        Old F2RAM = 12.998 s, RAM2F = 57.463 s
        New F2RAM = 6.396 s, RAM2F = 36.602 s, RAM2Fts = 60.689
        Size f_in = 59.797 MB,  f_old = 59.799 MB,  f_new = 44.452 MB,  f_nts = 59.799 MB
    RUN with duration 60 s, compression None, random True
        Old F2RAM = 6.494 s, RAM2F = 24.419 s
        New F2RAM = 5.027 s, RAM2F = 11.391 s, RAM2Fts = 25.679
        Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB

BB AI 64

    RUN with duration 60 s, compression lzf, random False
        Old F2RAM = 0.596 s, RAM2F = 2.383 s
        New F2RAM = 0.486 s, RAM2F = 1.262 s, RAM2Fts = 2.502
        Size f_in = 51.24 MB,  f_old = 51.252 MB,  f_new = 21.729 MB,  f_nts = 51.252 MB
    RUN with duration 60 s, compression 1, random False
        Old F2RAM = 0.868 s, RAM2F = 3.767 s
        New F2RAM = 0.636 s, RAM2F = 1.851 s, RAM2Fts = 3.819
        Size f_in = 25.203 MB,  f_old = 25.205 MB,  f_new = 9.859 MB,  f_nts = 25.205 MB
    RUN with duration 60 s, compression None, random False
        Old F2RAM = 0.331 s, RAM2F = 2.155 s
        New F2RAM = 0.374 s, RAM2F = 1.184 s, RAM2Fts = 1.514
        Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB
    RUN with duration 60 s, compression lzf, random True
        Old F2RAM = 0.521 s, RAM2F = 3.011 s
        New F2RAM = 0.384 s, RAM2F = 1.922 s, RAM2Fts = 4.538
        Size f_in = 75.344 MB,  f_old = 75.356 MB,  f_new = 45.832 MB,  f_nts = 75.356 MB
    RUN with duration 60 s, compression 1, random True
        Old F2RAM = 1.031 s, RAM2F = 5.732 s
        New F2RAM = 0.828 s, RAM2F = 3.852 s, RAM2Fts = 5.841
        Size f_in = 59.797 MB,  f_old = 59.799 MB,  f_new = 44.452 MB,  f_nts = 59.799 MB
    RUN with duration 60 s, compression None, random True
        Old F2RAM = 0.334 s, RAM2F = 1.41 s
        New F2RAM = 0.385 s, RAM2F = 0.849 s, RAM2Fts = 1.529
        Size f_in = 91.633 MB,  f_old = 91.633 MB,  f_new = 45.832 MB,  f_nts = 91.633 MB

learnings:
- h5py.directRW() does not make things faster for us -> plus code-quality is worse
- switching to lzf and omitting timestamp -> each brings 30% improvement -> adds up to ~50%
- worst case (var I & V, plus reading) can DOS the BBB with 117% load without writing any gpio
"""

import mmap
import time
from pathlib import Path
from timeit import timeit
from types import TracebackType

import numpy as np
from shepherd_core import Compression
from shepherd_core import Reader
from shepherd_core import Writer
from shepherd_core.data_models import EnergyDType
from typing_extensions import Self


class SharedMemory:
    def __init__(self, duration: int) -> None:
        self.buffer_size = Writer.samples_per_buffer * (2 * 4)
        self.buffer_count = duration * 10
        self.voltage_offset = 0
        self.current_offset = Writer.samples_per_buffer * 4

        self.size = self.buffer_count * self.buffer_size
        self.mapped_mem = mmap.mmap(
            -1,
            self.size,
            #    mmap.MAP_SHARED,
            #    mmap.PROT_WRITE,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
        extra_arg: int = 0,
    ) -> None:
        if self.mapped_mem is not None:
            self.mapped_mem.close()

    def read_old(self, index: int) -> (np.ndarray, np.ndarray):
        buffer_offset = self.buffer_size * index
        voltage = np.frombuffer(
            self.mapped_mem,
            "=u4",
            count=Writer.samples_per_buffer,
            offset=buffer_offset + self.voltage_offset,
        )
        current = np.frombuffer(
            self.mapped_mem,
            "=u4",
            count=Writer.samples_per_buffer,
            offset=buffer_offset + self.current_offset,
        )
        return voltage, current

    def write_old(
        self,
        index: int,
        voltage: np.ndarray,
        current: np.ndarray,
    ) -> None:
        buffer_offset = self.buffer_size * index
        self.mapped_mem.seek(buffer_offset)
        self.mapped_mem.write(voltage.tobytes())
        self.mapped_mem.write(current.tobytes())


def generate_harvest(
    path: Path,
    duration: int,
    compression: Compression,
    random: bool = True,
) -> None:
    rng = np.random.default_rng()
    samples_per_1s = Writer.samples_per_buffer * 10
    with Writer(
        path,
        mode="harvester",
        datatype=EnergyDType.ivsample,
        verbose=False,
        force_overwrite=True,
        compression=compression,
    ) as sw:
        sw.store_hostname("Hrv")
        for _iter in range(duration):
            if random:
                _v = rng.uniform(low=1.0, high=3.0, size=samples_per_1s)
                _i = rng.uniform(low=0.001, high=0.05, size=samples_per_1s)
            else:
                _v = np.linspace(3.30, 3.30, samples_per_1s)
                _i = np.linspace(100e-6, 2000e-6, samples_per_1s)
            sw.append_iv_data_si(timestamp=_iter, voltage=_v, current=_i)
        sw.h5file.flush()


def file_to_ram_old(path: Path, mem: SharedMemory) -> None:
    with Reader(path, verbose=False) as sr:
        buffer_index = 0
        for _, dsv, dsc in sr.read_buffers(start_n=0, is_raw=True):
            # TODO: cal.raw_to_si
            mem.write_old(buffer_index, dsv, dsc)
            buffer_index += 1


def ram_to_file_old(path: Path, mem: SharedMemory, compression: Compression) -> None:
    with Writer(
        path,
        mode="emulator",
        datatype=EnergyDType.ivsample,
        verbose=False,
        force_overwrite=True,
        compression=compression,
    ) as sw:
        sw.store_hostname("Emu")
        for _iter in range(mem.buffer_count):
            _v, _i = mem.read_old(_iter)
            sw.append_iv_data_raw(_iter / 10, _v, _i)
        sw.h5file.flush()


def file_to_ram_new(path: Path, mem: SharedMemory) -> None:
    with Reader(path, verbose=False) as sr:
        shared_array = np.ndarray(
            shape=(mem.size // 4,),
            dtype="u4",
            buffer=mem.mapped_mem,
        )
        for _iter in range(mem.buffer_count):
            m_start = 2 * Writer.samples_per_buffer * _iter
            m_end = 2 * Writer.samples_per_buffer * (_iter + 1)
            f_start = Writer.samples_per_buffer * _iter
            f_end = Writer.samples_per_buffer * (_iter + 1)
            sr.ds_voltage.read_direct(
                shared_array,
                np.s_[f_start:f_end],
                np.s_[m_start : m_start + Writer.samples_per_buffer],
            )
            sr.ds_current.read_direct(
                shared_array,
                np.s_[f_start:f_end],
                np.s_[m_start + Writer.samples_per_buffer : m_end],
            )


def ram_to_file_new(path: Path, mem: SharedMemory, compression: Compression) -> None:
    with Writer(
        path,
        mode="emulator",
        datatype=EnergyDType.ivsample,
        verbose=False,
        force_overwrite=True,
        compression=compression,
    ) as sw:
        sw.store_hostname("Emu")
        shared_array = np.ndarray(
            shape=(mem.size // 4,),
            dtype="u4",
            buffer=mem.mapped_mem,
        )
        for _iter in range(mem.buffer_count):
            m_start = 2 * Writer.samples_per_buffer * _iter
            m_end = 2 * Writer.samples_per_buffer * (_iter + 1)
            f_start = Writer.samples_per_buffer * _iter
            f_end = Writer.samples_per_buffer * (_iter + 1)
            if f_end > sw.ds_voltage.size:
                sw.ds_voltage.resize((f_end,))
                sw.ds_current.resize((f_end,))
            sw.ds_voltage.write_direct(
                shared_array,
                np.s_[m_start : m_start + Writer.samples_per_buffer],
                np.s_[f_start:f_end],
            )
            sw.ds_current.write_direct(
                shared_array,
                np.s_[m_start + Writer.samples_per_buffer : m_end],
                np.s_[f_start:f_end],
            )
        sw.h5file.flush()


def ram_to_file_new_ts(path: Path, mem: SharedMemory, compression: Compression) -> None:
    with Writer(
        path,
        mode="emulator",
        datatype=EnergyDType.ivsample,
        verbose=False,
        force_overwrite=True,
        compression=compression,
    ) as sw:
        sw.store_hostname("Emu")
        time_series_ns = sw.sample_interval_ns * np.arange(
            Writer.samples_per_buffer,
        ).astype("u8")

        shared_array = np.ndarray(
            shape=(mem.size // 4,),
            dtype="u4",
            buffer=mem.mapped_mem,
        )
        for _iter in range(mem.buffer_count):
            m_start = 2 * Writer.samples_per_buffer * _iter
            m_end = 2 * Writer.samples_per_buffer * (_iter + 1)
            f_start = Writer.samples_per_buffer * _iter
            f_end = Writer.samples_per_buffer * (_iter + 1)
            if f_end > sw.ds_voltage.size:
                sw.ds_time.resize((f_end,))
                sw.ds_voltage.resize((f_end,))
                sw.ds_current.resize((f_end,))
            sw.ds_time[f_start:f_end] = (
                _iter / 10 + time_series_ns
            )  # TODO: not really needed anymore
            sw.ds_voltage.write_direct(
                shared_array,
                np.s_[m_start : m_start + Writer.samples_per_buffer],
                np.s_[f_start:f_end],
            )
            sw.ds_current.write_direct(
                shared_array,
                np.s_[m_start + Writer.samples_per_buffer : m_end],
                np.s_[f_start:f_end],
            )
        sw.h5file.flush()


if __name__ == "__main__":
    compressions = [Compression.lzf, Compression.gzip1, Compression.null]
    path_i = Path(__file__).parent / "artiHrv.h5"
    path_o1 = Path(__file__).parent / "artiEmu1.h5"
    path_o2 = Path(__file__).parent / "artiEmu2.h5"
    path_o3 = Path(__file__).parent / "artiEmu3.h5"
    duration = 60

    for random in [False, True]:
        for compression in compressions:
            generate_harvest(path_i, duration, compression, random=random)

            with SharedMemory(duration) as mem:
                time.sleep(1)
                two = timeit(
                    "file_to_ram_old(path_i, mem)",
                    globals=globals(),
                    number=1,
                )
                time.sleep(1)
                tro = timeit(
                    "ram_to_file_old(path_o1, mem, compression)",
                    globals=globals(),
                    number=1,
                )
                # TODO: compare files - content should be identical
                time.sleep(1)
                twn = timeit(
                    "file_to_ram_new(path_i, mem)",
                    globals=globals(),
                    number=1,
                )
                time.sleep(1)
                trn = timeit(
                    "ram_to_file_new(path_o2, mem, compression)",
                    globals=globals(),
                    number=1,
                )
                trt = timeit(
                    "ram_to_file_new_ts(path_o3, mem, compression)",
                    globals=globals(),
                    number=1,
                )
                print(
                    f"RUN with "
                    f"duration {duration} s, "
                    f"compression {compression}, "
                    f"random {random}",
                )
                print(
                    f"\tOld "
                    f"F2RAM = {round(two, 3)} s, "
                    f"RAM2F = {round(tro, 3)} s",
                )
                print(
                    f"\tNew "
                    f"F2RAM = {round(twn, 3)} s, "
                    f"RAM2F = {round(trn, 3)} s, "
                    f"RAM2Fts = {round(trt, 3)}",
                )
                print(
                    f"\tSize "
                    f"f_in = {round(path_i.stat().st_size/2**20,3)} MB, "
                    f" f_old = {round(path_o1.stat().st_size/2**20,3)} MB, "
                    f" f_new = {round(path_o2.stat().st_size/2**20,3)} MB, "
                    f" f_nts = {round(path_o3.stat().st_size/2**20,3)} MB",
                )
                time.sleep(1)
                path_i.unlink()
                path_o1.unlink()
                path_o2.unlink()
                path_o3.unlink()
