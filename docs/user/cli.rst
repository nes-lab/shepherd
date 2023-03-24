Command-line tools
==================

Shepherd offers two command line utilities:

`Shepherd-herd`_ is the command line utility for remotely controlling a group of shepherd nodes.
This is the key user interface to shepherd.
The pure-python package is installed on the user's local machine and sends commands to the shepherd nodes over *ssh*.

To simplify usage you should set up an ansible style, YAML-formatted inventory file named ``herd.yml`` in either of these directories (with highest priority first):

- relative to your current working directory in ``inventory/herd.yml``
- in your local home-directory ``~/herd.yml``
- in the config path ``/etc/shepherd/herd.yml`` (**recommendation**)

Refer to the example ``herd.yml`` file in the ``inventory`` directory of the shepherd repository.

`Shepherd-sheep`_ is the command line utility for locally controlling a single shepherd node.
Depending on your use-case you may not even need to directly interact with it!

.. _shepherd-herd-cli:

shepherd-herd
-------------

.. click:: shepherd_herd:cli
   :prog: shepherd-herd
   :show-nested:

Examples
********

Installation, configuration and usage on the command-line is explained on the `PyPi - Project site <https://pypi.org/project/shepherd-herd/>`_.

shepherd-sheep
--------------

.. click:: shepherd.cli:cli
   :prog: shepherd-sheep
   :show-nested:


Examples
********

Coming soon …
