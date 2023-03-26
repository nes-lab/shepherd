.. SHEPHERD documentation main file, created by
   sphinx-quickstart on Thu Jun 27 19:11:40 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root 'toctree' directive.

Welcome to SHEPHERD's documentation
====================================

To learn how *shepherd* enables research into the most challenging problems of coordinating battery-less sensor nodes, take a look at our `paper <https://wwwpub.zih.tu-dresden.de/~mzimmerl/pubs/geissdoerfer19shepherd.pdf>`_.
To get a basic understanding of what shepherd does, read the :doc:`user/basics`.
If you have the hardware on your desk and want to get started, read :doc:`user/getting_started`.
To record/emulate data on a group of shepherd nodes, use the :ref:`shepherd-herd-cli` command line utility.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   user/basics
   user/getting_started
   user/hardware
   user/cli
   user/calibration
   user/data_format
   user/api
   user/performance
   user/virtual_source

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide

   dev/contributing
   dev/data_handling
   dev/sysfs
   dev/gps_sync
   dev/virtual_source
   dev/v2_improvements


.. toctree::
   :maxdepth: 2
   :caption: Student-Projects

   projects/implement_dataviewer.rst
   projects/improvement_for_memory_interface.rst
