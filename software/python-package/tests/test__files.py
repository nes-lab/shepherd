"""
check correctness of meta-files, mostly yaml, in & around the project

"""

from pathlib import Path

import pytest
from shepherd_core import CalibrationCape
from shepherd_core.data_models import VirtualSourceConfig
from shepherd_core.data_models.base.cal_measurement import CalMeasurementCape
from shepherd_core.data_models.task import EmulationTask
from shepherd_core.data_models.task import HarvestTask


@pytest.fixture
def path_here() -> Path:
    return Path(__file__).resolve().parent


def test_file_cal_data(path_here: Path) -> None:
    CalibrationCape.from_file(path_here / "_test_cal_data.yaml")


def test_file_cal_meas(path_here: Path) -> None:
    CalMeasurementCape.from_file(path_here / "_test_cal_meas.yaml")


def test_file_emulation(path_here: Path) -> None:
    EmulationTask.from_file(path_here / "_test_config_emulation.yaml")


def test_file_emulation_example(path_here: Path) -> None:
    EmulationTask.from_file(path_here.parent / "example_config_emulation.yaml")


def test_file_harvest(path_here: Path) -> None:
    HarvestTask.from_file(path_here / "_test_config_harvest.yaml")


def test_file_harvest_example(path_here: Path) -> None:
    HarvestTask.from_file(path_here.parent / "example_config_harvest.yaml")


def test_file_virtsource(path_here: Path) -> None:
    VirtualSourceConfig.from_file(path_here / "_test_config_virtsource.yaml")
