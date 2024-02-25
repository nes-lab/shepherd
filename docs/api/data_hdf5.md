# Shepherd-Data - HDF5 Reader & Writer

:::{note}
TODO: WORK IN PROGRESS
:::

These two classes allow the user to read and write shepherds hdf5-files.
For more details about the data-format you can read:

- doc for [](../user/data_format.md)
- [Reader-source](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/reader.py) in core-lib
- [Reader-source](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_data/shepherd_data/reader.py) in data-module (Inherits from core-reader)
- [Writer-source](https://github.com/orgua/shepherd-datalib/blob/main/shepherd_core/shepherd_core/writer.py)

## Usage-Example

This basic example can read & print some metadata from a hdf5-file.

```python
import shepherd_data as sd

with sd.Reader("./hrv_sawtooth_1h.h5") as db:
    print(f"Mode: {db.get_mode()}")
    print(f"Window: {db.get_window_samples()}")
    print(f"Config: {db.get_config()}")
```

## Reader

```{eval-rst}
.. autoclass:: shepherd_data.Reader
    :members:
    :inherited-members:
```

## Writer

```{eval-rst}
.. autoclass:: shepherd_data.Writer
    :members:
    :inherited-members:
```
