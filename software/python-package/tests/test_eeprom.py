from collections.abc import Generator

import pytest
from pyfakefs.fake_filesystem import FakeFilesystem
from shepherd_core import CalibrationCape
from shepherd_core.data_models.base.calibration import CapeData
from shepherd_sheep import EEPROM


@pytest.fixture
def cal_cape() -> CalibrationCape:
    return CalibrationCape()


@pytest.fixture
def cape_data() -> CapeData:
    return CapeData(serial_number="011900000001", version="00A0")


@pytest.fixture
def data_test_string() -> bytes:
    return b"test content"


@pytest.fixture
def eeprom_open(
    request: pytest.FixtureRequest,
    fake_fs: FakeFilesystem | None,
) -> Generator[EEPROM, None, None]:
    if fake_fs is not None:
        fake_fs.create_file("/sys/bus/i2c/devices/2-0054/eeprom", st_size=32768)
        request.applymarker(
            pytest.mark.xfail(
                raises=OSError,
                reason="pyfakefs doesn't support seek in files",
            ),
        )
    with EEPROM() as eeprom:
        yield eeprom


@pytest.fixture
def eeprom_retained(eeprom_open: EEPROM) -> Generator[EEPROM, None, None]:
    data = eeprom_open._read(0, 1024)
    for i in range(256):
        eeprom_open._write(i * 4, b"\xde\xad\xbe\xef")
    yield eeprom_open
    eeprom_open._write(0, data)


@pytest.fixture
def eeprom_with_data(
    eeprom_retained: EEPROM,
    cape_data: CapeData,
) -> Generator[EEPROM, None, None]:
    eeprom_retained._write_cape_data(cape_data)
    return eeprom_retained


@pytest.fixture
def eeprom_with_calibration(
    eeprom_retained: EEPROM,
    cal_cape: CalibrationCape,
) -> Generator[EEPROM, None, None]:
    eeprom_retained.write_calibration(cal_cape)
    return eeprom_retained


@pytest.mark.eeprom_write
@pytest.mark.hardware
def test_read_raw(eeprom_open: EEPROM) -> None:
    eeprom_open._read(0, 4)


@pytest.mark.eeprom_write
@pytest.mark.hardware
def test_write_raw(eeprom_retained: EEPROM, data_test_string: bytes) -> None:
    eeprom_retained._write(0, data_test_string)
    data = eeprom_retained._read(0, len(data_test_string))
    assert data == data_test_string


@pytest.mark.eeprom_write
@pytest.mark.hardware
def test_read_value(eeprom_with_data: EEPROM, cape_data: CapeData) -> None:
    with pytest.raises(KeyError):
        _ = eeprom_with_data["some non-sense parameter"]
    assert eeprom_with_data["version"] == cape_data["version"]


@pytest.mark.eeprom_write
@pytest.mark.hardware
def test_write_value(eeprom_retained: EEPROM, cape_data: CapeData) -> None:
    with pytest.raises(KeyError):
        eeprom_retained["some non-sense parameter"] = "some data"

    eeprom_retained["version"] = "1234"
    assert eeprom_retained["version"] == "1234"


@pytest.mark.eeprom_write
@pytest.mark.hardware
def test_write_capedata(eeprom_retained: EEPROM, cape_data: CapeData) -> None:
    eeprom_retained._write_cape_data(cape_data)
    for key, value in cape_data.items():
        if isinstance(value, str):
            assert eeprom_retained[key] == value.rstrip("\0")
        else:
            assert eeprom_retained[key] == value


@pytest.mark.eeprom_write
@pytest.mark.hardware
def test_read_capedata(eeprom_with_data: EEPROM, cape_data: CapeData) -> None:
    cape_data2 = eeprom_with_data.read_cape_data()
    for key, _ in cape_data:
        assert cape_data[key] == cape_data2[key]


@pytest.mark.eeprom_write
@pytest.mark.hardware
def test_write_calibration(eeprom_retained: EEPROM, cal_cape: CalibrationCape) -> None:
    eeprom_retained.write_calibration(cal_cape)
    cal_restored = eeprom_retained.read_calibration()
    for component in ["harvester", "emulator"]:
        assert cal_restored[component].get_hash() == cal_cape[component].get_hash()


@pytest.mark.eeprom_write
@pytest.mark.hardware
def test_read_calibration(
    eeprom_with_calibration: EEPROM,
    cal_cape: CalibrationCape,
) -> None:
    cal_restored = eeprom_with_calibration.read_calibration()
    for component in ["harvester", "emulator"]:
        assert cal_restored[component].get_hash() == cal_cape[component].get_hash()
