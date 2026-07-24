"""Worst Case (RNG) test.

- Variables: compression, randomness of data
- old: current design
- new: eval h5py.directRead()/Write() feature

"""

import mmap
import time
from pathlib import Path
from timeit import timeit
from types import TracebackType

import numpy as np
from shepherd_core.data_models.content.enum_datatypes import Compression
from shepherd_core.data_models.content.enum_datatypes import EnergyDType
from shepherd_core.logger import log
from shepherd_core.reader import Reader
from shepherd_core.writer import Writer
from typing_extensions import Self


class SharedMemory:
    def __init__(self, duration: int) -> None:
        self.buffer_size = Writer.CHUNK_SAMPLES_N * (2 * 4)
        self.buffer_count = duration * 10
        self.voltage_offset = 0
        self.current_offset = Writer.CHUNK_SAMPLES_N * 4

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
            count=Writer.CHUNK_SAMPLES_N,
            offset=buffer_offset + self.voltage_offset,
        )
        current = np.frombuffer(
            self.mapped_mem,
            "=u4",
            count=Writer.CHUNK_SAMPLES_N,
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
    *,
    random: bool = True,
) -> None:
    rng = np.random.default_rng()
    samples_per_1s = Writer.CHUNK_SAMPLES_N * 10
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
                v_ = rng.uniform(low=1.0, high=3.0, size=samples_per_1s)
                i_ = rng.uniform(low=0.001, high=0.05, size=samples_per_1s)
            else:
                v_ = np.linspace(3.30, 3.30, samples_per_1s)
                i_ = np.linspace(100e-6, 2000e-6, samples_per_1s)
            sw.append_iv_data_si(timestamp=_iter, voltage=v_, current=i_)
        sw.h5file.flush()


def file_to_ram_old(path: Path, mem: SharedMemory) -> None:
    with Reader(path, verbose=False) as sr:
        buffer_index = 0
        for _, dsv, dsc in sr.read(start_n=0, is_raw=True):
            # TODO: cal.raw_to_si
            mem.write_old(buffer_index, dsv, dsc)
            buffer_index += 1  # noqa: SIM113


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
            v_, i_ = mem.read_old(_iter)
            sw.append_iv_data_raw(_iter / 10, v_, i_)
        sw.h5file.flush()


def file_to_ram_new(path: Path, mem: SharedMemory) -> None:
    with Reader(path, verbose=False) as sr:
        shared_array = np.ndarray(
            shape=(mem.size // 4,),
            dtype=np.uint32,
            buffer=mem.mapped_mem,
        )
        for _iter in range(mem.buffer_count):
            m_start = 2 * Writer.CHUNK_SAMPLES_N * _iter
            m_end = 2 * Writer.CHUNK_SAMPLES_N * (_iter + 1)
            f_start = Writer.CHUNK_SAMPLES_N * _iter
            f_end = Writer.CHUNK_SAMPLES_N * (_iter + 1)
            sr.ds_voltage.read_direct(
                shared_array,
                np.s_[f_start:f_end],
                np.s_[m_start : m_start + Writer.CHUNK_SAMPLES_N],
            )
            sr.ds_current.read_direct(
                shared_array,
                np.s_[f_start:f_end],
                np.s_[m_start + Writer.CHUNK_SAMPLES_N : m_end],
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
            dtype=np.uint32,
            buffer=mem.mapped_mem,
        )
        for _iter in range(mem.buffer_count):
            m_start = 2 * Writer.CHUNK_SAMPLES_N * _iter
            m_end = 2 * Writer.CHUNK_SAMPLES_N * (_iter + 1)
            f_start = Writer.CHUNK_SAMPLES_N * _iter
            f_end = Writer.CHUNK_SAMPLES_N * (_iter + 1)
            if f_end > sw.ds_voltage.size:
                sw.ds_voltage.resize((f_end,))
                sw.ds_current.resize((f_end,))
            sw.ds_voltage.write_direct(
                shared_array,
                np.s_[m_start : m_start + Writer.CHUNK_SAMPLES_N],
                np.s_[f_start:f_end],
            )
            sw.ds_current.write_direct(
                shared_array,
                np.s_[m_start + Writer.CHUNK_SAMPLES_N : m_end],
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
            Writer.CHUNK_SAMPLES_N,
        ).astype(np.uint64)

        shared_array = np.ndarray(
            shape=(mem.size // 4,),
            dtype=np.uint32,
            buffer=mem.mapped_mem,
        )
        for _iter in range(mem.buffer_count):
            m_start = 2 * Writer.CHUNK_SAMPLES_N * _iter
            m_end = 2 * Writer.CHUNK_SAMPLES_N * (_iter + 1)
            f_start = Writer.CHUNK_SAMPLES_N * _iter
            f_end = Writer.CHUNK_SAMPLES_N * (_iter + 1)
            if f_end > sw.ds_voltage.size:
                sw.ds_time.resize((f_end,))
                sw.ds_voltage.resize((f_end,))
                sw.ds_current.resize((f_end,))
            sw.ds_time[f_start:f_end] = (
                _iter / 10 + time_series_ns
            )  # TODO: not really needed anymore
            sw.ds_voltage.write_direct(
                shared_array,
                np.s_[m_start : m_start + Writer.CHUNK_SAMPLES_N],
                np.s_[f_start:f_end],
            )
            sw.ds_current.write_direct(
                shared_array,
                np.s_[m_start + Writer.CHUNK_SAMPLES_N : m_end],
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
                log.info(
                    "RUN with duration %d s, compression %s, random %s",
                    duration,
                    str(compression),
                    str(random),
                )
                log.info(
                    "\tOld F2RAM = %f s, RAM2F = %f s",
                    round(two, 3),
                    round(tro, 3),
                )
                log.info(
                    "\tNew F2RAM = %f s, RAM2F = %f s, RAM2Fts = %f",
                    round(twn, 3),
                    round(trn, 3),
                    round(trt, 3),
                )
                log.info(
                    "\tSize f_in = %f MB, f_old = %f MB, f_new = %f MB, f_nts = %f MB",
                    round(path_i.stat().st_size / 2**20, 3),
                    round(path_o1.stat().st_size / 2**20, 3),
                    round(path_o2.stat().st_size / 2**20, 3),
                    round(path_o3.stat().st_size / 2**20, 3),
                )
                time.sleep(1)
                path_i.unlink()
                path_o1.unlink()
                path_o2.unlink()
                path_o3.unlink()
