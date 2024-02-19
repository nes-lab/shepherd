# Data format

Data is stored in the popular [Hierarchical Data Format](https://en.wikipedia.org/wiki/Hierarchical_Data_Format).

This section describes the essential structure of data recorded with shepherd:

```text
    .
    |-- attributes
    |   `-- mode
    |-- data
    |   |-- datatype
    |   |-- window_samples
    |   |-- time
    |   |   `-- attributes
    |   |       |-- gain
    |   |       `-- offset
    |   |-- current
    |   |   `-- attributes
    |   |       |-- gain
    |   |       `-- offset
    |   `-- voltage
    |       `-- attributes
    |           |-- gain
    |           `-- offset
    `-- gpio
        |-- time
        `-- values
```

The `mode` attribute allows to distinguish between data from the harvester and emulator.

The data group contains the actual IV data and can consist of (datatypes):

- `ivsample`s ⇾ continuous samples,
- `ivcurve`s ⇾ characterizing voltage ramps with a specific step-size (needs `window_samples` to be set to step count)
- `ìsc_voc` ⇾ a sample pair of open circuit voltage and short circuit current

The datasets `time`, `current` and `voltage` are raw `uint32` (directly from ADC, when possible) and can be converted to their physical equivalent using the corresponding `gain` and `offset` attributes. For better documentation and automatic processing there are additional attributes attached to the datasets (not shown above):

- `unit` contains the SI unit for the scaling operation
- `description` shows how to apply the scaling, i.e. `system time [s] = value * gain + (offset)`

See also [](calibration).

The gpio group stores the timestamp when a GPIO edge was detected and the corresponding bit mask in values.
For example, assume that all are were low at the beginning of the recording.
At time T, GPIO pin 2 goes high.
The value 0x04 will be stored together with the timestamp T in nanoseconds.

:::{note}
There is more data and metadate, like system logs, included in the files created by the testbed. Check the reference-links below for a deeper dive.
:::

There are numerous tools to work with HDF5 and library bindings for all popular programming languages.

We offer the [core-library](https://pypi.org/project/shepherd_core) and complementing CLI-wrapper called [shepherd-data](https://pypi.org/project/shepherd_data). Advantages are:

- automatic validation upon opening a recording
- extraction of iv-data including optional down-sampling
- extraction of system logs
- generate overview of file-content and -structure (meta-data)
- plotting of files
  - specific files or whole directories
  - overviews or even specific parts within a time-window

Here's an example how to plot data recorded with shepherd using bare Python:

```python
import h5py
import matplotlib.pyplot as plt

f, axarr = plt.subplots(1, 2)
with h5py.File("rec.h5", "r") as hf:
    # convert time to seconds
    t_gain = hf["data"]["time"].attrs["gain"]
    t_offset = hf["data"]["time"].attrs["offset"]
    time = hf["data"]["time"][:].astype(float) * t_gain + t_offset
    for i, var in enumerate(["voltage", "current", "time"]):
        gain = hf["data"][var].attrs["gain"]
        offset = hf["data"][var].attrs["offset"]
        values = hf["data"][var][:] * gain + offset
        axarr[i].plot(time, values)

plt.show()
```

## References

- [core/writer.py](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/writer.py) to see the complete file-structure
- [core/reader.py](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/reader.py) for file-reading, -validation, -extractions and -conversions
- [data/reader.py](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_data/shepherd_data/reader.py) for higher functions like resampling, plotting and extracting metadata
