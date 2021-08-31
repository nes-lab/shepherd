import copy
import numpy as np
import h5py
from scipy import signal


def downsample_signal(
    dataset: h5py.Dataset, ds_factor: int, block_len: int = None
):
    # https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.decimate.html
    ds_factor_max = 12  # iir restriction
    ds_factor_list = list([])
    while ds_factor > ds_factor_max:
        ds_factor_list.append(ds_factor_max)
        ds_factor = int(ds_factor / ds_factor_max)
    ds_factor_list.append(ds_factor)

    if block_len is None:
        n_blocks = 100  # Aim for 100 blocks
        block_len = int(len(dataset) / n_blocks)
    else:
        n_blocks = int(len(dataset) / block_len)

    block_ds_len = copy.deepcopy(block_len)
    for ds_factor_local in ds_factor_list:
        block_ds_len = round(block_ds_len / ds_factor_local)

    sig_ds = np.empty((block_ds_len * n_blocks,))
    for i in range(n_blocks):
        sig_block = dataset[i * block_len : (i + 1) * block_len]
        for ds_factor_local in ds_factor_list:
            sig_block = signal.decimate(sig_block[:], q=ds_factor_local, ftype="iir")
        sig_ds[i * block_ds_len: (i + 1) * block_ds_len] = sig_block[:]
        print(f"block {i+1}/{n_blocks} done")
    return sig_ds


def downsample_time(time, ds_factor: int, block_len: int = 1000000):
    n_blocks = int(len(time) / block_len)

    block_ds_len = int(block_len / ds_factor)
    time_ds = np.empty((block_ds_len * n_blocks,))
    for i in range(n_blocks):
        time_ds[i * block_ds_len : (i + 1) * block_ds_len] = time[
            i * block_len : (i + 1) * block_len : ds_factor
        ]

    return time_ds
