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
- smaller original cache is a bit faster
- larger hdf5-chunks compress better
- writing larger chunks to datasets brings better performance
    - even if file-chunks are smaller) has

1MiB Cache

    Chunks(inp=10000,h5ds=10000)    = 14.037 s, 10 reps, 2.487 MiB
    Chunks(inp=10000,h5ds=20000)    = 14.641 s, 10 reps, 2.379 MiB
    Chunks(inp=10000,h5ds=50000)    = 15.216 s, 10 reps, 2.326 MiB
    Chunks(inp=10000,h5ds=100000)   = 16.437 s, 10 reps, 2.303 MiB

    Chunks(inp=20000,h5ds=10000)    = 11.191 s, 10 reps, 2.487 MiB
    Chunks(inp=20000,h5ds=20000)    = 10.758 s, 10 reps, 2.384 MiB
    Chunks(inp=20000,h5ds=50000)    = 12.770 s, 10 reps, 2.302 MiB
    Chunks(inp=20000,h5ds=100000)   = 14.024 s, 10 reps, 2.272 MiB

    Chunks(inp=50000,h5ds=10000)    = 9.413 s, 10 reps, 2.485 MiB
    Chunks(inp=50000,h5ds=20000)    = 9.365 s, 10 reps, 2.380 MiB
    Chunks(inp=50000,h5ds=50000)    = 9.921 s, 10 reps, 2.319 MiB
    Chunks(inp=50000,h5ds=100000)   = 12.385 s, 10 reps, 2.288 MiB

    Chunks(inp=100000,h5ds=10000)   = 8.782 s, 10 reps, 2.483 MiB
    Chunks(inp=100000,h5ds=20000)   = 8.462 s, 10 reps, 2.381 MiB
    Chunks(inp=100000,h5ds=50000)   = 9.226 s, 10 reps, 2.320 MiB
    Chunks(inp=100000,h5ds=100000)  = 10.240 s, 10 reps, 2.296 MiB

Cache-explosion

    Chunks(inp=10000,h5ds=200000)   = 134.154 s, 10 reps, 2.335 MiB
    Chunks(inp=10000,h5ds=300000)   = 191.523 s, 10 reps, 2.344 MiB
    Chunks(inp=10000,h5ds=400000)   = 250.807 s, 10 reps, 2.399 MiB
    Chunks(inp=10000,h5ds=500000)   = 310.579 s, 10 reps, 2.334 MiB

8MiB Cache (default for libhdf5 v2)

    Chunks(inp=10000,h5ds=10000)    = 13.759 s, 10 reps, 2.487 MiB
    Chunks(inp=10000,h5ds=20000)    = 15.039 s, 10 reps, 2.379 MiB
    Chunks(inp=10000,h5ds=50000)    = 15.735 s, 10 reps, 2.326 MiB
    Chunks(inp=10000,h5ds=100000)   = 17.045 s, 10 reps, 2.303 MiB
    Chunks(inp=10000,h5ds=200000)   = 16.884 s, 10 reps, 2.290 MiB
    Chunks(inp=10000,h5ds=300000)   = 18.624 s, 10 reps, 2.312 MiB
    Chunks(inp=10000,h5ds=400000)   = 18.543 s, 10 reps, 2.320 MiB
    Chunks(inp=10000,h5ds=500000)   = 17.261 s, 10 reps, 2.286 MiB
    Chunks(inp=10000,h5ds=600000)   = 18.469 s, 10 reps, 2.329 MiB
    Chunks(inp=10000,h5ds=700000)   = 19.799 s, 10 reps, 2.341 MiB
    Chunks(inp=10000,h5ds=800000)   = 21.331 s, 10 reps, 2.360 MiB

    Chunks(inp=20000,h5ds=10000)    = 11.282 s, 10 reps, 2.487 MiB
    Chunks(inp=20000,h5ds=20000)    = 11.014 s, 10 reps, 2.384 MiB
    Chunks(inp=20000,h5ds=50000)    = 13.978 s, 10 reps, 2.302 MiB
    Chunks(inp=20000,h5ds=100000)   = 14.650 s, 10 reps, 2.272 MiB
    Chunks(inp=20000,h5ds=200000)   = 14.468 s, 10 reps, 2.259 MiB
    Chunks(inp=20000,h5ds=300000)   = 16.279 s, 10 reps, 2.284 MiB
    Chunks(inp=20000,h5ds=400000)   = 16.190 s, 10 reps, 2.286 MiB
    Chunks(inp=20000,h5ds=500000)   = 14.828 s, 10 reps, 2.253 MiB
    Chunks(inp=20000,h5ds=600000)   = 16.072 s, 10 reps, 2.298 MiB
    Chunks(inp=20000,h5ds=700000)   = 17.414 s, 10 reps, 2.316 MiB
    Chunks(inp=20000,h5ds=800000)   = 18.766 s, 10 reps, 2.332 MiB

    Chunks(inp=50000,h5ds=10000)    = 9.650 s, 10 reps, 2.485 MiB
    Chunks(inp=50000,h5ds=20000)    = 9.813 s, 10 reps, 2.380 MiB
    Chunks(inp=50000,h5ds=50000)    = 10.867 s, 10 reps, 2.319 MiB
    Chunks(inp=50000,h5ds=100000)   = 13.090 s, 10 reps, 2.288 MiB
    Chunks(inp=50000,h5ds=200000)   = 12.923 s, 10 reps, 2.269 MiB
    Chunks(inp=50000,h5ds=300000)   = 14.721 s, 10 reps, 2.296 MiB
    Chunks(inp=50000,h5ds=400000)   = 14.698 s, 10 reps, 2.298 MiB
    Chunks(inp=50000,h5ds=500000)   = 13.320 s, 10 reps, 2.263 MiB
    Chunks(inp=50000,h5ds=600000)   = 14.572 s, 10 reps, 2.306 MiB
    Chunks(inp=50000,h5ds=700000)   = 15.930 s, 10 reps, 2.323 MiB
    Chunks(inp=50000,h5ds=800000)   = 17.274 s, 10 reps, 2.338 MiB

    Chunks(inp=100000,h5ds=10000)   = 8.836 s, 10 reps, 2.483 MiB
    Chunks(inp=100000,h5ds=20000)   = 8.716 s, 10 reps, 2.381 MiB
    Chunks(inp=100000,h5ds=50000)   = 10.103 s, 10 reps, 2.320 MiB
    Chunks(inp=100000,h5ds=100000)  = 10.618 s, 10 reps, 2.296 MiB
    Chunks(inp=100000,h5ds=200000)  = 11.739 s, 10 reps, 2.277 MiB
    Chunks(inp=100000,h5ds=300000)  = 12.837 s, 10 reps, 2.302 MiB
    Chunks(inp=100000,h5ds=400000)  = 12.719 s, 10 reps, 2.305 MiB
    Chunks(inp=100000,h5ds=500000)  = 11.975 s, 10 reps, 2.268 MiB
    Chunks(inp=100000,h5ds=600000)  = 13.184 s, 10 reps, 2.314 MiB
    Chunks(inp=100000,h5ds=700000)  = 14.510 s, 10 reps, 2.329 MiB
    Chunks(inp=100000,h5ds=800000)  = 16.109 s, 10 reps, 2.345 MiB

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
    ds_time = h5file["data"]["time"]
    ds_data = h5file["data"]["value"]
    position = 0
    for inp_time, inp_data in chunks:
        len_add = len(inp_time)
        pos_end = position + len_add
        data_length = len(ds_time)
        if pos_end >= data_length:
            data_length += increment
            ds_time.resize((data_length,))
            ds_data.resize((data_length,))
        ds_time[position:pos_end] = inp_time
        ds_data[position:pos_end] = inp_data
        position = pos_end
    h5file.flush()


if __name__ == "__main__":
    path = path_storage / "hrv_performance_meas.hrv5"
    repetitions = 10
    duration = 10
    sample_rate = 100_000
    samples_total = duration * sample_rate

    dtypes = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}

    inc_factor = 10
    byte_n = 2
    shuffle = True
    h5_cache_size = 8 * 2**20  # 1MiB default

    _iters = itertools.product(
        [10_000, 20_000, 50_000, 100_000],  # input-chunk-size
        [
            10_000,
            20_000,
            50_000,
            100_000,
            200_000,
            300_000,
            400_000,
            500_000,
            600_000,
            700_000,
            800_000,
        ],  # h5-chunk-size
    )
    for inp_chunk_size, h5_chunk_size in _iters:
        _opts = f"Chunks(inp={inp_chunk_size},h5ds={h5_chunk_size})"

        if inp_chunk_size != h5_chunk_size and 8 * h5_chunk_size > h5_cache_size:
            continue

        rng = np.random.default_rng()
        timeseries = commons.SAMPLE_INTERVAL_NS * np.arange(inp_chunk_size).astype(np.uint64)
        timestamp = 1791741342 * 10**9

        chunks_n = samples_total // inp_chunk_size
        chunks = []

        for _iter in range(chunks_n):
            chunk_time = timeseries + timestamp + _iter * commons.SAMPLE_INTERVAL_NS
            chunk_data = rng.integers(
                low=0, high=2 ** (8 * byte_n), size=inp_chunk_size, dtype=dtypes[byte_n]
            )
            chunks.append((chunk_time, chunk_data))

        if path.exists():
            path.unlink()

        increment = inc_factor * h5_chunk_size

        with h5py.File(path, "w", libver="latest", rdcc_w0=1, rdcc_nbytes=h5_cache_size) as h5file:
            h5file.create_group("data")
            h5file["data"].create_dataset(
                name="time",
                shape=(increment,),
                dtype="u8",
                maxshape=(None,),
                chunks=(h5_chunk_size,),
                compression=Compression.lzf,
                shuffle=shuffle,
                scaleoffset=None,
            )
            h5file["data"].create_dataset(
                name="value",
                shape=(increment,),
                dtype=f"u{byte_n}",
                maxshape=(None,),
                chunks=(h5_chunk_size,),
                compression=Compression.lzf,
                shuffle=shuffle,
                scaleoffset=None,
            )

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
