import gc
from collections.abc import Generator
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path

import pytest
from click.testing import CliRunner
from pyfakefs.fake_filesystem import FakeFilesystem
from shepherd_sheep.sysfs_interface import reload_kernel_module
from shepherd_sheep.sysfs_interface import remove_kernel_module


def check_beagleboard() -> bool:
    with suppress(Exception), Path("/proc/cpuinfo").open(encoding="utf-8-sig") as info:
        if "AM33XX" in info.read():
            return True
    return False


@pytest.fixture(
    params=[
        pytest.param("real_hardware", marks=pytest.mark.hardware),
        pytest.param("mock_hardware", marks=pytest.mark.mock_hardware),
    ],
)
def fake_fs(
    request: pytest.FixtureRequest,
) -> Generator[FakeFilesystem | None, None, None]:
    if request.param == "mock_hardware":
        request.fixturenames.append("fs")  # needs pyfakefs installed
        fake_sysfs: FakeFilesystem = request.getfixturevalue("fs")
        fake_sysfs.create_dir("/sys/class/remoteproc/remoteproc1")
        fake_sysfs.create_dir("/sys/class/remoteproc/remoteproc2")
        yield fake_sysfs
    else:
        yield None


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--eeprom-write",
        action="store_true",
        default=False,
        help="run tests that require to disable eeprom write protect",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: Iterable[pytest.Item],
) -> None:
    skip_mock = pytest.mark.skip(reason="cannot be mocked")
    skip_eeprom_write = pytest.mark.skip(reason="requires --eeprom-write option")
    skip_missing_hardware = pytest.mark.skip(reason="no hw to test on")
    real_hardware = check_beagleboard()

    for item in items:
        if "hardware" in item.keywords and not real_hardware:
            item.add_marker(skip_missing_hardware)
        if "eeprom_write" in item.keywords and not config.getoption("--eeprom-write"):
            item.add_marker(skip_eeprom_write)
        if "mock_hardware" in item.keywords and "hardware" in item.keywords:
            # real_hardware
            item.add_marker(skip_mock)


@pytest.fixture
def _shepherd_down(fake_fs: FakeFilesystem | None) -> None:
    if fake_fs is None:
        remove_kernel_module()


@pytest.fixture
def _shepherd_up(
    _shepherd_down: None,
    fake_fs: FakeFilesystem | None,
) -> Generator[None, None, None]:
    if fake_fs is not None:
        files = [
            ("/sys/shepherd/state", "idle"),
            ("/sys/shepherd/time_start", "0"),
            ("/sys/shepherd/time_stop", "0"),
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
            ("/sys/shepherd/pru_msg_box", "0"),
            ("/sys/shepherd/programmer/protocol", "0"),
            ("/sys/shepherd/programmer/datarate", "0"),
            ("/sys/shepherd/programmer/datasize", "0"),
            ("/sys/shepherd/programmer/pin_tck", "0"),
            ("/sys/shepherd/programmer/pin_tdio", "0"),
            ("/sys/shepherd/programmer/pin_tdo", "0"),
            ("/sys/shepherd/programmer/pin_tms", "0"),
            ("/sys/shepherd/memory/iv_inp_address", "0"),
            ("/sys/shepherd/memory/iv_inp_size", "0"),
            ("/sys/shepherd/memory/iv_out_address", "0"),
            ("/sys/shepherd/memory/iv_out_size", "0"),
            ("/sys/shepherd/memory/gpio_address", "0"),
            ("/sys/shepherd/memory/gpio_size", "0"),
            ("/sys/shepherd/memory/util_address", "0"),
            ("/sys/shepherd/memory/util_size", "0"),
            # TODO: design tests for programmer, also check if all hardware-tests need real hw
            #       -> there should be more tests that don't require a pru
        ]
        for file_, content in files:
            fake_fs.create_file(file_, contents=content)
        here = Path(__file__).resolve().parent
        fake_fs.add_real_file(here / "_test_config_emulation.yaml")
        fake_fs.add_real_file(here / "_test_config_harvest.yaml")
        fake_fs.add_real_file(here / "_test_config_virtsource.yaml")
        yield
    else:
        reload_kernel_module()
        yield
        gc.collect()  # precaution


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
