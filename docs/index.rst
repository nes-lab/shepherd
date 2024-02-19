
Welcome to SHEPHERD's documentation
====================================

This is the main entry point into the shepherd ecosystem. Based on your experience, you might skip the first steps:

#. To learn how *shepherd* enables research into the most challenging problems of coordinating battery-less sensor nodes, take a look at our `paper <https://wwwpub.zih.tu-dresden.de/~mzimmerl/pubs/geissdoerfer19shepherd.pdf>`_.
#. To get a basic understanding of what shepherd does, start with the :doc:`user/basics`.
#. If you have the hardware on your desk and want to get started, read :doc:`user/getting_started`.
#. To record/emulate data on a group of shepherd nodes, use the :ref:`herd-cli` command line utility.
#. To access the testbed-instance go to :doc:`external/testbed`.
#. If you'd like to contribute or have issues, try the :doc:`dev/contributing`-guide or jump to the :doc:`user/help_me_help_you`-section.
#. The DevLog-Documentation is in: https://orgua.github.io/shepherd_v2_planning/

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
   user/help_me_help_you

.. toctree::
   :maxdepth: 2
   :caption: Testbed & Tools

   external/testbed
   external/shepherd_core
   external/shepherd_data
   external/shepherd_targets
   external/shepherd_webservice

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
   :caption: Analyzing Sync-Behavior

   timesync/1_prepare_software
   timesync/2_setup_hardware
   timesync/3_measurement
   timesync/4_analysis
