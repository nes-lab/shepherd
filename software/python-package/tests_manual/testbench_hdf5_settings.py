"""
Specs:
- sheep writes datasets in parallel
- ~ 15 datasets, with 3 or 5 or 6 fast-growing:
    - iv-trace & timestamp with 100 kSps (2x u4, 1x u8)
    - gpio-trace & timestamp (u2, u8) with var frequency (up to 3 MSps)
    - UART & timestamp (string, u8) with var frequency
- chunk size of the fast-growing datasets is 10 k to 100 k elements
- chunks are always written fully, no reading back
- code runs on an old armv7-platform
- data is stored to sd-card OR to NAS via nfs on the testbed


Learning:
- compression=lzf is a good compromise
    - much smaller files
    - gzip seems to have not only more overhead, but also shows latency issues?!?
- shuffle=True is usually a good idea (awesome for timestamps)
    - gpio-trace even with only 1 bit changing is performing worse!
- resizing dataset with factor 100x of chunk-size is fine (safes metadata access, IO-Roundtrip)
    - IV-Recorder can also determine the final size and set it!
- rdcc_w0 = 1 is fine for our use-case
    - makes sure that full chunks are written to disk and not kept in RAM
- libver=latest is also fine for us (we have v110) - might have better chunking & performance
-

Results:
    Cache/rdcc:  (0,    521,    1048576,    0.75) -> defaults for beaglebone
                 (_mdc, _nslots, _nbytes, _w0)


u8,chunk_size=50000,time,shuffle=False,scaleoffset=None    = 8.533 s for 10 reps, 4.917 MiB
u8,chunk_size=50000,time,shuffle=False,scaleoffset=0       = 12.558 s for 10 reps, 3.459 MiB
u8,chunk_size=50000,time,shuffle=True,scaleoffset=None     = 4.457 s for 10 reps, 0.409 MiB
u8,chunk_size=50000,time,shuffle=True,scaleoffset=0        = 11.575 s for 10 reps, 3.459 MiB

u8,chunk_size=400000,time,shuffle=False,scaleoffset=None   = 6.529 s for 10 reps, 3.934 MiB
u8,chunk_size=400000,time,shuffle=False,scaleoffset=0      = 10.065 s for 10 reps, 3.054 MiB
u8,chunk_size=400000,time,shuffle=True,scaleoffset=None    = 3.859 s for 10 reps, 0.297 MiB
u8,chunk_size=400000,time,shuffle=True,scaleoffset=0       = 4.877 s for 10 reps, 0.214 MiB

    -> scale-offset does harm!
    -> shuffle helps a lot!

u2,chunk_size=50000,random,shuffle=False,scaleoffset=None  = 5.279 s for 10 reps, 1.909 MiB
u2,chunk_size=50000,random,shuffle=False,scaleoffset=0     = 5.468 s for 10 reps, 1.910 MiB
u2,chunk_size=50000,random,shuffle=True,scaleoffset=None   = 5.429 s for 10 reps, 1.909 MiB
u2,chunk_size=50000,random,shuffle=True,scaleoffset=0      = 5.620 s for 10 reps, 1.910 MiB

u2,chunk_size=400000,random,shuffle=False,scaleoffset=None = 3.990 s for 10 reps, 1.528 MiB
u2,chunk_size=400000,random,shuffle=False,scaleoffset=0    = 4.107 s for 10 reps, 1.528 MiB
u2,chunk_size=400000,random,shuffle=True,scaleoffset=None  = 4.220 s for 10 reps, 1.528 MiB
u2,chunk_size=400000,random,shuffle=True,scaleoffset=0     = 4.336 s for 10 reps, 1.528 MiB

u8,chunk_size=50000,random,shuffle=False,scaleoffset=None  = 19.108 s for 10 reps, 7.631 MiB
u8,chunk_size=50000,random,shuffle=False,scaleoffset=0     = 18.939 s for 10 reps, 7.632 MiB
u8,chunk_size=50000,random,shuffle=True,scaleoffset=None   = 20.683 s for 10 reps, 7.631 MiB
u8,chunk_size=50000,random,shuffle=True,scaleoffset=0      = 20.846 s for 10 reps, 7.632 MiB

u8,chunk_size=400000,random,shuffle=False,scaleoffset=None = 15.319 s for 10 reps, 6.105 MiB
u8,chunk_size=400000,random,shuffle=False,scaleoffset=0    = 15.946 s for 10 reps, 6.106 MiB
u8,chunk_size=400000,random,shuffle=True,scaleoffset=None  = 17.680 s for 10 reps, 6.105 MiB
u8,chunk_size=400000,random,shuffle=True,scaleoffset=0     = 18.221 s for 10 reps, 6.106 MiB

    -> random is worst case input
    -> shuffle and scale-offset both hurt a bit (shuffle hurts more on larger chunks)
    -> larger chunks improve compression & runtime
"""

import itertools
import time
from pathlib import Path
from timeit import timeit

import h5py
import numpy as np
from shepherd_core import Compression
from shepherd_core.logger import log
from shepherd_sheep import commons

path_storage = Path("/var/shepherd/recordings")


def h5_write_op(h5file: h5py.File, chunks: list, increment: int) -> None:
    dset = h5file["data"]["test"]
    position = 0
    for chunk in chunks:
        len_add = len(chunk)
        pos_end = position + len_add
        data_length = len(dset)
        if pos_end >= data_length:
            data_length += increment
            dset.resize((data_length,))
        dset[position:pos_end] = chunk
        position = pos_end
    h5file.flush()


if __name__ == "__main__":
    path = path_storage / "hrv_performance_meas.hrv5"
    repetitions = 10
    duration = 10
    sample_rate = 100_000
    samples_total = duration * sample_rate

    dtypes = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}

    debug = False
    auto_chunk = False  # -> always worse, too small!
    libver = "latest"  # no harm for us, might bring perf
    rdcc_w0 = 1  # exactly our usecase
    inc_factor = 10

    _iters = itertools.product(
        [2, 8],  # byte_n, of dataset
        [50_000, 100_000, 200_000, 400_000],  # chunk-size
        ["time", "random"],  # data-type
        [False, True],  # shuffle, for more efficient storage (supports compression)
        [None, 0],  # scale_offset, 0=auto-scale
    )
    for byte_n, chunk_size, dtype, shuffle, scale_offset in _iters:
        _opts = (
            f"u{byte_n},chunk_size={chunk_size},{dtype},"
            f"shuffle={shuffle},scaleoffset={scale_offset}"
        )
        chunks_n = samples_total // chunk_size
        if dtype == "random":
            rng = np.random.default_rng()
            chunks = [
                rng.integers(low=0, high=2 ** (8 * byte_n), size=chunk_size, dtype=dtypes[byte_n])
                for _ in range(chunks_n)
            ]
        elif dtype == "time":
            if byte_n != 8:
                continue
            timestamp = 1791741342 * 10**9
            timeseries = commons.SAMPLE_INTERVAL_NS * np.arange(chunk_size).astype(np.uint64)
            chunks = [
                timeseries + timestamp + _iter * commons.SAMPLE_INTERVAL_NS
                for _iter in range(chunks_n)
            ]
        else:
            continue
        if path.exists():
            path.unlink()

        with h5py.File(path, "w", libver=libver, rdcc_w0=rdcc_w0) as h5file:
            h5file.create_group("data")
            h5file["data"].create_dataset(
                name="test",
                shape=(chunk_size,),
                dtype=f"u{byte_n}",
                maxshape=(None,),
                chunks=True if auto_chunk else (chunk_size,),
                compression=Compression.lzf,
                shuffle=shuffle,
                scaleoffset=scale_offset,
            )

            if debug:
                log.info(f"Libver: {h5file.libver}")
                log.info(f"Cache:  {h5file.id.get_access_plist().get_cache()}")
            if auto_chunk:
                log.info(h5file["data"]["test"].chunks)
            increment = inc_factor * chunk_size
            time.sleep(3)
            time_total = timeit(
                "h5_write_op(h5file, chunks, increment)",
                globals=globals(),
                number=repetitions,
            )
            fsize = path.stat().st_size / 2**20
            log.info(
                "%s\t= %.3f s, %d reps, %.3f MiB",
                _opts,
                time_total,
                repetitions,
                fsize,
            )
