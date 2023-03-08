import os
import shutil

from Cython.Build import cythonize
from setuptools import Extension

from setuptools import setup

# copy source files over to avoid mixup of absolute and relative paths
external_src = [
    "../pru0-shepherd-fw/virtual_converter.c",
    "../pru0-shepherd-fw/calibration.c",
    "../pru0-shepherd-fw/math64_safe.c",
]
if not os.path.isdir("./build"):
    os.makedirs("./build")
for src in external_src:
    shutil.copy(src, "./build/" + src.split("/")[-1])


module_vconv = Extension(
    name="Cvirtual_converter",
    sources=[
        "Cvirtual_converter.pyx",
        "build/virtual_converter.c",
        "build/calibration.c",
        "build/math64_safe.c",
    ],
    include_dirs=[
        "./../pru0-shepherd-fw/include/",
        "./../pru0-shepherd-fw/",
        "./../include/",
        "./../lib/src/",
        "./../lib/include/",
    ],
    define_macros=[("__CYTHON__", "1"), ("PRU0", "1")],
    language="c",
)

setup(
    name="pru_virtual_converter",
    description="model of the virtual converter / source based on c",
    version="0.0.1",
    ext_modules=cythonize(
        [module_vconv],
        annotate=True,
    ),
    
)


