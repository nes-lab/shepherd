import gc
import subprocess  # noqa: S404
import time
from contextlib import suppress
from pathlib import Path

import pytest


def check_beagleboard():
    with suppress(Exception), open("/proc/cpuinfo") as info:
        if "AM33XX" in info.read():
            return True
    return False


@pytest.fixture(
    params=[
        pytest.param("real_hardware", marks=pytest.mark.hardware),
        pytest.param("fake_hardware", marks=pytest.mark.fake_hardware),
    ]
)
def fake_hardware(request):
    if request.param == "fake_hardware":
        request.fixturenames.append("fs")
        fake_sysfs = request.getfixturevalue("fs")
        fake_sysfs.create_dir("/sys/class/remoteproc/remoteproc1")
        fake_sysfs.create_dir("/sys/class/remoteproc/remoteproc2")
        yield fake_sysfs
    else:
        yield None


def pytest_addoption(parser):
    parser.addoption(
        "--eeprom-write",
        action="store_true",
        default=False,
        help="run tests that require to disable eeprom write protect",
    )


def pytest_collection_modifyitems(config, items):
    # skip_fake = pytest.mark.skip(reason="this needs real hardware to run")
    skip_eeprom_write = pytest.mark.skip(reason="requires --eeprom-write option to run")
    skip_missing_hardware = pytest.mark.skip(reason="no hardware to test on")
    real_hardware = check_beagleboard()

    for item in items:
        if "hardware" in item.keywords and not real_hardware:
            item.add_marker(skip_missing_hardware)
        if "eeprom_write" in item.keywords and not config.getoption("--eeprom-write"):
            item.add_marker(skip_eeprom_write)


@pytest.fixture()
def shepherd_up(fake_hardware, shepherd_down):
    if fake_hardware is not None:
        files = [
            ("/sys/shepherd/state", "idle"),
            ("/sys/shepherd/mode", "harvester"),
            ("/sys/shepherd/n_buffers", "1"),
            ("/sys/shepherd/memory/address", "1"),
            ("/sys/shepherd/memory/size", "1"),
            ("/sys/shepherd/samples_per_buffer", "1"),
            ("/sys/shepherd/buffer_period_ns", "1"),
            ("/sys/shepherd/dac_auxiliary_voltage_raw", "0"),
            ("/sys/shepherd/calibration_settings", "0"),
            ("/sys/shepherd/virtual_converter_settings", "0"),
            ("/sys/shepherd/virtual_harvester_settings", "0"),
            ("/sys/shepherd/programmer/protocol", "0"),
            ("/sys/shepherd/programmer/datarate", "0"),
            ("/sys/shepherd/programmer/pin_tck", "0"),
            ("/sys/shepherd/programmer/pin_tdio", "0"),
            ("/sys/shepherd/programmer/pin_tdo", "0"),
            ("/sys/shepherd/programmer/pin_tms", "0"),
            # TODO: design tests for programmer, also check if all hardware-tests need real hw
            #       -> there should be more tests that don't require a pru
        ]
        for file_, content in files:
            fake_hardware.create_file(file_, contents=content)
        here = Path(__file__).absolute().parent
        shpk = here.parent / "shepherd"
        fake_hardware.add_real_file(here / "example_config_harvester.yml")
        fake_hardware.add_real_file(here / "example_config_virtsource.yml")
        fake_hardware.add_real_file(shpk / "virtual_harvester_defs.yml")
        fake_hardware.add_real_file(shpk / "virtual_source_defs.yml")
        yield
    else:
        subprocess.run(["modprobe", "shepherd"], timeout=60)  # noqa: S607 S603
        time.sleep(3)
        yield
        subprocess.run(["rmmod", "shepherd"], timeout=60)  # noqa: S607 S603
        gc.collect()  # precaution
        time.sleep(3)


@pytest.fixture()
def shepherd_down(fake_hardware):
    if fake_hardware is None:
        subprocess.run(["rmmod", "shepherd"], timeout=60)  # noqa: S607 S603
        time.sleep(3)
