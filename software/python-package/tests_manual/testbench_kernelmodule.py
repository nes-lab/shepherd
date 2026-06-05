""" """

import time
from timeit import timeit

from shepherd_sheep.logger import log
from shepherd_sheep.logger import set_verbosity
from shepherd_sheep.sys_access import kernel_module_is_active as check_v3
from shepherd_sheep.sys_access import reload_kernel_module as reload_v3
from testbench_kernelmodule_fn_v1 import check_sys_access as check_v1
from testbench_kernelmodule_fn_v1 import reload_kernel_module as reload_v1
from testbench_kernelmodule_fn_v2 import check_sys_access as check_v2
from testbench_kernelmodule_fn_v2 import reload_kernel_module as reload_v2


def reload_and_check_v1() -> bool:
    """takes ~6.0 s minimum (was originally 8), rarely ~45 s"""
    reload_v1()
    return check_v1()


def reload_and_check_v2() -> bool:
    """takes 0.695 s (mean over 100iterations), rarely ~30 s (seem gone)"""
    reload_v2()
    return check_v2()


def reload_and_check_v3() -> bool:
    """latest sheep-implementation with minor improvements since v2.

    takes 0.695 s (mean over 100iterations), min is 380 ms, rarely ~30 s"""
    reload_v3()
    return check_v3()


if __name__ == "__main__":
    set_verbosity()

    for routine_under_test in [
        "reload_and_check_v3()",
        "reload_and_check_v2()",
        "reload_and_check_v1()",
    ]:
        repetitions = 100
        time_total = 0
        for _i in range(repetitions):
            time.sleep(1)
            kmod = timeit(
                routine_under_test,
                globals=globals(),
                number=1,
            )
            log.info("\tKMod %s_i%d = %.3f s", routine_under_test, _i, kmod)
            time_total += kmod
        log.info("\t -> mean = %.3f s", time_total / repetitions)
