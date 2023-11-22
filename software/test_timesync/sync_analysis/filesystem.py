import os
from .logger import logger
from pathlib import Path


def get_files(
    start_path: Path, stem: str = "", suffix: str = ".log", recursion_depth: int = 0
) -> list:
    if recursion_depth == 0:
        suffix = suffix.lower().split(".")[-1]
    #if start_path.is_file():
    #    dir
    dir_items = os.scandir(start_path)
    recursion_depth += 1
    files = []

    for item in dir_items:
        if item.is_dir():
            files += get_files(item.path, stem, suffix, recursion_depth)
            continue
        else:
            item_name = str(item.name).lower()
            item_ext = item_name.split(".")[-1]
            if item_ext == suffix and item_ext != item_name and stem in item_name:
                files.append(Path(item.path))
            if suffix == "" and item_ext == item_name:
                files.append(Path(item.path))
    if recursion_depth == 1 and len(files) > 0:
        logger.debug(" -> got %s files with the suffix '%s'", len(files), suffix)
    return files
