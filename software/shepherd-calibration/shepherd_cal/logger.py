import logging
from typing import Union

logger = logging.getLogger("shp.calTool")
logger.setLevel(logging.INFO)


def set_verbosity(state: Union[bool, int] = True) -> None:
    if isinstance(state, bool):
        # strange solution -> bool is also int, so it falls through below in elif
        if not state:
            return
    elif isinstance(state, int) and state < 3:
        return  # old format, will be replaced
    logger.setLevel(logging.DEBUG)
