# -*- coding: utf-8 -*-
import pytest
from pathlib import Path

from shepherd import CalibrationData


@pytest.fixture
def data_meas_example_yml():
    here = Path(__file__).absolute()
    name = "example_cal_meas.yml"
    return here.parent / name


@pytest.fixture
def data_example_yml():
    here = Path(__file__).absolute()
    name = "example_cal_data.yml"
    return here.parent / name


@pytest.fixture()
def default_cal():
    return CalibrationData.from_default()


@pytest.fixture()
def default_bytestr(default_cal):
    return default_cal.to_bytestr()


def test_from_default():
    _ = CalibrationData.from_default()


def test_from_yaml(data_example_yml):
    _ = CalibrationData.from_yaml(data_example_yml)


def test_from_measurements(data_meas_example_yml):
    _ = CalibrationData.from_measurements(data_meas_example_yml)


def test_to_bytestr(default_cal):
    default_cal.to_bytestr()


def test_from_bytestr(default_bytestr):
    _ = CalibrationData.from_bytestr(default_bytestr)
