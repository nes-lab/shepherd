import os
import shutil
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension
from setuptools import setup

# copy source files over to avoid mixup of absolute and relative paths
external_src = [
    "../pru0-shepherd-fw/virtual_converter.c",
    "../pru0-shepherd-fw/calibration.c",
    "../pru0-shepherd-fw/math64_safe.c",
]
build_path = Path(__file__) / "build"
if not build_path.is_dir():
    build_path.mkdir(parents=True)
for src in external_src:
    shutil.copy(src, build_path / src.split("/")[-1])


module_vconv = Extension(
    name="virtual_converter",
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
