API
===

The shepherd API offers high level access to shepherd's functionality and forms the base for the two command line utilities.
Note that the API only converts local functionality on a single shepherd node.
Use the ``shepherd-herd`` command line utility to orchestrate a group of shepherd nodes remotely.

Recorder
--------

The recorder is used to configure all relevant hardware and software and to sample and extract data from the analog frontend.

.. autoclass:: shepherd_sheep.Recorder
   :members:
   :inherited-members:

Usage:

.. code-block:: python

    # Configure converter for fixed 1.5V input regulation
    with Recorder(harvesting_voltage=1.5) as recorder:
        recorder.start()

        for _ in range(100):
            idx, buf = recorder.get_buffer()
            recorder.release_buffer(idx)


Emulator
--------

The emulator is used to replay previously recorded IV data to an attached sensor node.

.. autoclass:: shepherd_sheep.Emulator
   :members:
   :inherited-members:

Usage:

.. code-block:: python

    # We'll read existing data using a Reader for the Shepherd-file
    lr = shepherd_data.Reader("mylog.h5")
    with ExitStack() as stack:
        stack.enter_context(lr)
        emu = Emulator(
            calibration_recording=lr.get_calibration_data(),
            initial_buffers=lr.read_buffers(end=64),
        )
        stack.enter_context(emu)
        emu.start()

        for hrvst_buf in lr.read_buffers(start=64):
            idx, _ = emu.get_buffer()
            emu.put_buffer(idx, hrvst_buf)


LogWriter
---------

The *LogWriter* is used to store IV data sampled with shepherd to an hdf5 file.

.. autoclass:: shepherd_sheep.LogWriter
   :members:

Usage:


.. code-block:: python

    with LogWriter("mylog.h5") as log_writer, Recorder() as recorder:
        recorder.start()
        for _ in range(100):
            idx, buf = recorder.get_buffer()
            log_writer.write_buffer(buf)
            recorder.release_buffer(idx)


LogReader
------------

The *Reader* for shepherd-files is used to read previously recorded data from an hdf5 file buffer by buffer.
It can be used with the Emulator to replay recorded data to an attached sensor node.


.. autoclass:: shepherd_sheep.LogReader
   :members:

Usage:

.. code-block:: python

    with shepherd.LogReader("mylog.h5") as log_reader:
        for buf in log_reader.read_buffers(end=1000):
            print(len(buf))

.. note::
    These inner parts will be refactored to a reusable module called ``shepherd-core`` containing a basic reader and writer for the shepherd files and reusable data-models. A ready to use version for users is the `shepherd-datalib <https://pypi.org/project/shepherd-data>`_.
