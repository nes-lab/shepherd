from .commons import CAPE_HW_VER

if CAPE_HW_VER == 25:
    from .target_io_v25 import TargetIO
    from .target_io_v25 import target_pins
else:
    from .target_io_v24 import TargetIO
    from .target_io_v24 import target_pins

__all__ = ["TargetIO", "target_pins"]
