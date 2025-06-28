"""Benchmark for Resampling of emu-output.

Warning: default .mean() uses float64, which causes
         a panic on the beaglebone (system halts randomly)

Prepare Input       11.54it/s
u32-Reshape         79.84it/s
Reshape-u32         82.23it/s
Reshape-Copy-u32    24.48it/s
Reshape-u64         31.31it/s -> no difference to version with clip and recast
Reshape-Copy-u64    16.11it/s
Slicer              34652.21it/s

"""

import numpy as np
from shepherd_core.logger import log
from tqdm import tqdm

rng = np.random.default_rng()
reduction_factor = 100
iterations = 80

data = [
    rng.integers(low=0, high=2**18, size=1_000_000, dtype=np.uint32)
    for _ in tqdm(range(iterations), desc="Prepare Input")
]


for i in tqdm(range(iterations), desc="u32-Reshape"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = data[i][0:len_add2].reshape(len_new, reduction_factor).mean(axis=1, dtype=np.uint32)
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Reshape-u32"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = np.reshape(data[i][0:len_add2], (len_new, reduction_factor)).mean(
        axis=1, dtype=np.uint32
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)

for i in tqdm(range(iterations), desc="Reshape-Copy-u32"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = np.reshape(data[i][0:len_add2], (len_new, reduction_factor), copy=True).mean(
        axis=1, dtype=np.uint32
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Reshape-u64"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = np.reshape(data[i][0:len_add2], (len_new, reduction_factor)).mean(
        axis=1, dtype=np.uint64
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Reshape-u64-Final"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = (
        data[i][0:len_add2]
        .reshape(len_new, reduction_factor)
        .mean(axis=1, dtype=np.uint64)
        .clip(0, 2**32)
        .astype(np.uint32)
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Reshape-Copy-u64"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = np.reshape(data[i][0:len_add2], (len_new, reduction_factor), copy=True).mean(
        axis=1, dtype=np.uint64
    )
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)


for i in tqdm(range(iterations), desc="Slicer"):
    len_add1 = len(data[i])
    len_new = len_add1 // reduction_factor
    len_add2 = len_new * reduction_factor
    if len_add1 != len_add2:
        log.warning("Vectors had unequal length (%d vs %d)", len_add1, len_add2)
    _new = data[i][0:len_add2:reduction_factor]  # .copy()
    if _new.shape[0] != len_new:
        log.warning("Vector has not predicted length: %d vs %d", _new.shape[0], len_new)
