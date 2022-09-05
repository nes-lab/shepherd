Contributing
============

This section helps developers getting started with contributing to `shepherd`.

Codestyle
---------

Please stick to the C and Python codestyle guidelines provided with the source code.

All Python code is supposed to be formatted using `Black <https://black.readthedocs.io/en/stable/>`_ and `Flake8 <https://flake8.pycqa.org/en/latest/>`_ linter including some addons for cleaner and more secure code.

C code shall be formatted according to the Linux kernel C codesytle guide.
We provide the corresponding `clang-format` config as `.clang-format` in the repository's root directory.

Many IDEs/editors allow to automatically format code using the corresponding formatter and codestyle.
Please make use of this feature or otherwise integrate automatic codestyle formatting into your workflow.
See `Releasing`_ for more details on our `pre-commit <https://pre-commit.com/>`_-workflow.

Development setup
-----------------

While some parts of the `shepherd` software stack can be developed hardware independent, in most cases you will need to develop/test code on the actual target hardware.

We found the following setup convenient: Have the code on your laptop/workstation and use your editor/IDE to develop code.
Have a BeagleBone (potentially with `shepherd` hardware) connected to the same network as your workstation.
Prepare the BeagleBone by running the `bootstrap.yml` ansible playbook and additionally applying the `deploy/dev-host` ansible role.

You can now either use the ansible `deploy/sheep` role to push the changed code to the target and build and install it there.
Running the role takes significant time though as all components (kernel module, firmware and python package) are built.

Alternative 1: Some IDEs/editors allow to automatically push changes via ssh to the target. The directory ´/opt/shepherd´ is used as the projects root-dir on the beaglebone.
In addition the playbook `deploy/dev_rebuild_sw.yml` builds and installs all local source on target (conveniently without a restart).

Alternative 2: You can mirror your working copy of the `shepherd` code to the BeagleBone using a network file system.
We provide a playbook (`deploy/setup-dev-nfs.yml`) to conveniently configure an `NFS` share from your local machine to the BeagleBone.
After mounting the share on the BeagleBone, you can compile and install the corresponding software component remotely over ssh on the BeagleBone while editing the code locally on your machine.
Or you use the playbook described in "alternative 1".


Building debian packages (Deprecated)
-------------------------------------

`shepherd` software is packaged and distributed as debian packages.
Building these packages requires a large number of libraries and tools to be installed.
This motivates the use of docker for creating an isolated and well defined build environment.

The procedure for building the image, creating a container, copying the code into the container, building the packages and copying the artifacts back to the host are found in the `.travis.yml` in the repository's root directory.


Building the docs
-----------------

Make sure you have the python requirements installed:

.. code-block:: bash

    pip install --upgrade pip pipenv wheel setuptools

    pipenv install

Activate the `pipenv` environment:

.. code-block:: bash

    pipenv shell

Change into the docs directory and build the html documentation

.. code-block:: bash

    cd docs
    make html

The build is found at `docs/_build/html`. You can view it by starting a simple http server:

.. code-block:: bash

    cd _build/html
    python -m http.server

Now navigate your browser to `localhost:8000` to view the documentation.

Tests
-----

There is an initial testing framework that covers a large portion of the python code.
You should always make sure the tests are passing before committing your code.

To run the python tests, have a copy of the source code on a BeagleBone.
Build and install from source (see `Development setup`_ for more).
Change into the `software/python-package` directory and run the following commands to:
- install dependencies of tests
- run testbench

.. code-block:: bash

    sudo pip3 install -e ./[tests] --force-reinstall

    pytest

Releasing
---------

Before committing to the repository please run our `pre-commit <https://pre-commit.com/>`_-workflow. It will handle formatting and linters python-code. This is also one of the implemented tests in Github Action for QA for every pull request.

Make sure you have pre-commit installed:

.. code-block:: bash

    pip install pre-commit

Now you can either install an automatic hook for git that gets executed before committing:

.. code-block:: bash

    pre-commit install

Or you can just run the pre-commit checks:

.. code-block:: bash

    pre-commit run --all-files

Once you have a clean stable version of code, you should decide if your release is a patch, minor or major (see `Semantic Versioning <https://semver.org/>`_).
Make sure you're on the master branch and have a clean working directory.
Use `bump2version` to update the version number across the repository:

.. code-block:: bash

    bump2version --tag patch

Finally, push the changes and the tag to trigger the CI pipeline to build and deploy new debian packages to the server:

.. code-block:: bash

    git push origin master --tags
