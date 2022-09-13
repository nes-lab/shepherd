## Cython Compiled Lib

This directory contains setup for compiling the virtual converter / harvester / source as a shared library and use it in python to: 
- compare it to reference implementation
- enable unittesting of sub-functions

### Install prerequisites

choose what is needed

```Shell
cd .\pru0_cython_module

pip3 install pipenv

pipenv shell
```

### Compile Module

```Shell
python3 setup.py build_ext --inplace
```

### Cleanup

This should be the correct command, but it fails to clean up some pieces.

```Shell
python setup.py clean --all
```

### TODO

done: 
- replaced distutils by setuptools (as distutils are deprecated)
- implemented some compile-constants alter behaviour of c-code (no hw-dependency)
- used established folder-structure ... this code can now live in shepherd/software/firmware/pru0-cython-module
- switched to cython-prerelease to allow "volatile" (pipenv usage)
- use py3 code in cython -> language_level=... in .pyx file
- more detailed / explicit cython-config in setup.py
- some more FNs uncommented (/activated) in .pyx/pxd
- changed import in pyx-file to "cimport hvirtual_converter" to allow py-FNs with same name as c-FNs
  - are same names wanted??? this change was just a guess
- wrote a readme to help using the code
- ... lib compiles

todo: 
- testing.py fails -> functions in calibration.h are "undefined symbol"
  - maybe it just needs another "cdef extern from 'calibration.h'"
- structs still unknown to cython
  - maybe another "cdef extern from ..."
