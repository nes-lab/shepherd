from Cython.Build import cythonize
from setuptools import Extension
from setuptools import setup

setup(
    ext_modules=cythonize(
        Extension(
            "Cvirtual_converter",
            ["Cvirtual_converter.pyx", "./../pru0-shepherd-fw/virtual_converter.c"],
            define_macros=[("__CYTHON__", "1"), ("PRU0", "1")],
            include_dirs=[
                "./../pru0-shepherd-fw/include/",
                "./../pru0-shepherd-fw/",
                "./../include/",
                "./../lib/src/",
                "./../lib/include/",
            ],
            language="c",
        ),
        annotate=True,
    )
)
