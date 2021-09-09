import h5py
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import click
from scipy.signal import decimate
from datetime import datetime
from scipy import signal
import logging


logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)


def downsample(
    dataset: h5py.Dataset,
    ds_factor: int,
    is_time: bool,
    block_len: int = None,
):

    data_len = len(dataset)
    if block_len is None:
        block_len = min(10_000_000, data_len // 50)

    logging.debug(
        f"Downsampling {data_len} samples in blocks of {block_len} samples"
    )

    block_ds_len = int(block_len / ds_factor)
    block_len = block_ds_len * ds_factor
    n_blocks = int(data_len / block_len)

    dataset_dst_len = block_ds_len * n_blocks

    sig_ds = np.empty((dataset_dst_len,))
    if not is_time:
        # 8th order butterworth filter for downsampling
        # note: cheby1 does not work well for static outputs (2.8V can become 2.0V for buck-converters)
        flt = signal.iirfilter(
            N=8,
            Wn=1 / ds_factor,
            btype="lowpass",
            output="sos",
            ftype="butter",
        )
        gain = dataset.attrs["gain"]
        offset = dataset.attrs["offset"]

        # filter state
        z = np.zeros((flt.shape[0], 2))

    for i in range(n_blocks):
        slice_src = dataset[i * block_len : (i + 1) * block_len]
        # TODO: converting data to physical units would be more efficient after downsampling
        if is_time:
            y = slice_src[::ds_factor][:block_ds_len].astype(float) * 1e-9
        else:
            y, z = signal.sosfilt(flt, slice_src, zi=z)
            y = y[::ds_factor][:block_ds_len] * gain + offset
            y[y < 0] = 0

        sig_ds[i * block_ds_len : (i + 1) * block_ds_len] = y
        logging.debug(f"Block {i+1}/{n_blocks} done")
    return sig_ds


def extract_hdf(hdf_file: Path, ds_factor: int = 1):
    with h5py.File(hdf_file, "r") as hf:
        data = dict()

        for var in ["voltage", "current"]:
            if ds_factor > 1:
                logging.info(f"Starting downsampling of {var} signal")
                data[var] = downsample(hf["data"][var], ds_factor, False)
            else:
                gain = hf["data"][var].attrs["gain"]
                offset = hf["data"][var].attrs["offset"]
                data[var] = hf["data"][var][:].astype(float) * gain + offset

        if ds_factor > 1:
            logging.info(f"Starting downsampling of time data")
            data["time"] = downsample(hf["data"]["time"], ds_factor, True)
        else:
            data["time"] = hf["data"]["time"][:].astype(float) / 10**9

        data_len = min(
            [len(data["time"]), len(data["voltage"]), len(data["current"])]
        )
        data["time"] = data["time"][:data_len]
        data["current"] = data["current"][:data_len]
        data["voltage"] = data["voltage"][:data_len]
        # detect and warn about unusual time-jumps (hints to bugs or data-corruption)
        time_diff = hf["data"]["time"][1:data_len] - hf["data"]["time"][0:data_len-1]
        diff_count = np.asarray(np.unique(time_diff, return_counts=True))
        if diff_count.size > 2:  # array contains tuple of (value, count)
            logging.warning(f"time-delta seems to be changing \n{diff_count}")
        logging.debug(
            f"HDF from extracted -> resulting in {data_len} (downsampled) entries .."
        )

    return data


@click.command(short_help="Plot shepherd data from DIR")
@click.option("--directory", "-d", type=click.Path(exists=True))
@click.option("--filename", "-f", type=click.Path(), default="rec.h5")
@click.option("--sampling-rate", "-s", type=int, default=1000)
@click.option("--limit", "-l", type=str)
def cli(directory, filename, sampling_rate, limit):

    ds_factor = int(100_000 / sampling_rate)
    f, axes = plt.subplots(2, 1, sharex=True)
    f.suptitle(f"Voltage and current @ {sampling_rate} Hz")

    if directory is None:
        hdf_file = Path(filename)
        if not hdf_file.exists():
            raise click.FileError(str(hdf_file), hint="File not found")
        data = extract_hdf(hdf_file, ds_factor=ds_factor)
        axes[0].plot(data["time"] - data["time"][0], data["voltage"])  # add: ,label=active_node
        axes[1].plot(data["time"] - data["time"][0], data["current"] * 10**6)
        rt_start = datetime.fromtimestamp(data["time"][0])
        rt_end = datetime.fromtimestamp(data["time"][-1])
        logging.info(f"from {rt_start} to {rt_end}")
        active_nodes = ["TheHost"]
    else:
        data = dict()
        pl_dir = Path(directory)

        if limit:
            active_nodes = limit.split(",")
        else:
            active_nodes = [
                child.stem for child in pl_dir.iterdir() if child.is_dir()
            ]

        for child in pl_dir.iterdir():
            if not child.stem in active_nodes:
                continue

            hdf_file = child / filename
            if not hdf_file.exists():
                raise click.FileError(str(hdf_file), hint="File not found")
            hostname = child.stem
            logging.info(f"Opening {hostname} data")
            data[hostname] = extract_hdf(hdf_file, ds_factor=ds_factor)

        ts_start = min([data[hostname]["time"][0] for hostname in active_nodes])

        for hostname in active_nodes:
            rt_start = datetime.fromtimestamp(data[hostname]["time"][0])
            rt_end = datetime.fromtimestamp(data[hostname]["time"][-1])

            logging.info(f"{hostname}: from {rt_start} to {rt_end}")
            axes[0].plot(
                data[hostname]["time"] - ts_start,
                data[hostname]["voltage"],
                label=hostname,
            )
            axes[1].plot(
                data[hostname]["time"] - ts_start,
                data[hostname]["current"] * 10**6,
                label=hostname,
            )

    axes[0].set_ylabel("voltage [V]")
    axes[1].set_ylabel(r"current [$\mu$A]")
    axes[0].legend(loc="lower center", ncol=len(active_nodes))
    axes[1].set_xlabel("time [s]")
    plt.show()


if __name__ == "__main__":
    cli()
