Contributing
============

This section helps developers getting started with contributing to ``shepherd``.

Codestyle
---------

Please stick to the C and Python codestyle guidelines provided with the source code.

All **Python code** uses the feature-set of **version 3.8** is supposed to be formatted using `Black <https://black.readthedocs.io/en/stable/>`_ in default mode and is tested with the `Flake8 <https://flake8.pycqa.org/en/latest/>`_ linter including some addons for cleaner and more secure code.

**C code** uses the feature-set of **C99** and shall be formatted based on *LLVM*-Style with some alterations to make it easier to read, similar to python code.
We provide the corresponding ``clang-format`` config as ``.clang-format`` in the repository's root directory.

Many IDEs/editors allow to automatically format code using the corresponding formatter and codestyle.

To ensure basic quality standards we implemented the `pre-commit <https://pre-commit.com/>`_-workflow into the repo. It will

- handle formatting for python and C code (automatically)
- linters python, C, YAML, TOML, reStructuredText (rst), ansible playbooks
- it specially warns about security-related issues and deprecated features in python and C code

Pull Requests to the main branch will be tested online with *Github Actions*.

Make sure you have pre-commit installed:

.. code-block:: bash

    pip3 install pre-commit
    sudo apt install cppcheck

Now you can either install an automatic hook for git that gets executed before committing:

.. code-block:: bash

    pre-commit install

Or you can just run the pre-commit checks:

.. code-block:: bash

    pre-commit run --all-files

Development setup
-----------------

While some parts of the ``shepherd`` software stack can be developed hardware independent, in most cases you will need to develop/test code on the actual target hardware.

We found the following setup convenient: Have the code on your laptop/workstation and use your editor/IDE to develop code.
Have a BeagleBone (potentially with ``shepherd`` hardware) connected to the same network as your workstation.
Prepare the BeagleBone by running the ``bootstrap.yml`` ansible playbook and additionally applying the ``deploy/dev_host`` ansible role.

You can now either use the ansible ``deploy/sheep`` role to push the changed code to the target and build and install it there.
Running the role takes significant time though as all components (kernel module, firmware and python package) are built.

Alternative 1: Some IDEs/editors allow to automatically push changes via ssh to the target. The directory ´/opt/shepherd´ is used as the projects root-dir on the beaglebone.
In addition the playbook ``deploy/dev_rebuild_sw.yml`` builds and installs all local source on target (conveniently without a restart).

Alternative 2: You can mirror your working copy of the ``shepherd`` code to the BeagleBone using a network file system.
We provide a playbook (``deploy/setup-dev-nfs.yml``) to conveniently configure an ``NFS`` share from your local machine to the BeagleBone.
After mounting the share on the BeagleBone, you can compile and install the corresponding software component remotely over ssh on the BeagleBone while editing the code locally on your machine.
Or you use the playbook described in "alternative 1".


Building the docs
-----------------

Make sure you have the python requirements installed:

.. code-block:: bash

    pip install --upgrade pip pipenv wheel setuptools

    pipenv install

Activate the ``pipenv`` environment:

.. code-block:: bash

    pipenv shell

Change into the docs directory and build the html documentation

.. code-block:: bash

    cd docs
    make html

The build is found at ``docs/_build/html``. You can view it by starting a simple http server:

.. code-block:: bash

    cd _build/html
    python -m http.server

Now navigate your browser to ``localhost:8000`` to view the documentation.

Tests
-----

There is an initial testing framework that covers a large portion of the python code.
You should always make sure the tests are passing before committing your code.

To run the full range of python tests, have a copy of the source code on a BeagleBone.
Build and install from source (see `Development setup`_ for more).
Change into the ``software/python-package`` directory and run the following commands to:

- install dependencies of tests
- run testbench

.. code-block:: bash

    sudo pip3 install ./[tests]

    sudo pytest

Some tests (~40) are hardware-independent, while most of them require a beaglebone to work (~100). The testbench detects the BeagleBone automatically. A small subset (~8) tests writing & configuring the EEPROM on the shepherd cape and must be enabled manually (``sudo pytest --eeprom-write``)

**Note:** Recently the testbench had trouble running through completely and therefore losing the debug-output. It is probably caused by repeatedly loading & unloading the shepherd kernel module. The following commands allow to :

- run single tests,
- whole test-files or
- end the testbench after x Errors.

.. code-block:: bash

    sudo pytest tests/test_sheep_cli.py::test_cli_emulate_aux_voltage

    sudo pytest tests/test_sheep_cli.py

    sudo pytest --maxfail=1


Releasing
---------

Before committing to the repository please run our `pre-commit <https://pre-commit.com/>`_-workflow described in `Codestyle`_.

Once you have a clean stable version of code, you should decide if your release is a patch, minor or major (see `Semantic Versioning <https://semver.org/>`_). Make sure you're on the main branch and have a clean working directory.
Use ``bump2version`` to update the version number across the repository:

.. code-block:: bash

    bump2version --tag patch

Finally, push the changes and the tag to trigger the CI pipeline to build and deploy new debian packages to the server:

.. code-block:: bash

    git push origin main --tags
