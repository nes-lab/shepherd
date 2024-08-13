import math

import pytest
from shepherd_pru._virtual_pru import virtual_pru


@pytest.mark.parametrize("val1", [0, 6, 2**16, 2**32-1])
@pytest.mark.parametrize("val2", [0, 6, 2**16, 2**32-1])
def test_mul32(val1: int, val2: int) -> None:
    val_ref = min(2**32-1, max(0, val1 * val2))
    assert virtual_pru.mul32(val1, val2) == val_ref


@pytest.mark.parametrize("val1", [0, 6, 2**32-1, 2**64-1])
@pytest.mark.parametrize("val2", [0, 6, 2**32-1, 2**64-1])
def test_mul64(val1: int, val2: int) -> None:
    # todo: 2**32 as val is edge-case that causes trouble
    val_ref = min(2**64-1, max(0, val1 * val2))
    assert virtual_pru.mul64(val1, val2) == val_ref


@pytest.mark.parametrize("val1", [0, 6, 2**31, 2**31+1, 2**32-1])
@pytest.mark.parametrize("val2", [0, 6, 2**31, 2**31+1, 2**32-1])
def test_add32(val1: int, val2: int) -> None:
    val_ref = min(2**32-1, max(0, val1 + val2))
    assert virtual_pru.add32(val1, val2) == val_ref


@pytest.mark.parametrize("val1", [0, 6, 2**63, 2**63+1, 2**64-1])
@pytest.mark.parametrize("val2", [0, 6, 2**63, 2**63+1, 2**64-1])
def test_add64(val1: int, val2: int) -> None:
    val_ref = min(2**64-1, max(0, val1 + val2))
    assert virtual_pru.add64(val1, val2) == val_ref

@pytest.mark.parametrize("val1", [0, 6, 2**31-1, 2**31, 2**31+1, 2**32-1])
@pytest.mark.parametrize("val2", [0, 6, 2**31-1, 2**31, 2**31+1, 2**32-1])
def test_sub32(val1: int, val2: int) -> None:
    val_ref = min(2**32-1, max(0, val1 - val2))
    assert virtual_pru.sub32(val1, val2) == val_ref


@pytest.mark.parametrize("val1", [0, 6, 2**63, 2**63+1, 2**64-1])
@pytest.mark.parametrize("val2", [0, 6, 2**63, 2**63+1, 2**64-1])
def test_sub64(val1: int, val2: int) -> None:
    val_ref = min(2**64-1, max(0, val1 - val2))
    assert virtual_pru.sub64(val1, val2) == val_ref


@pytest.mark.parametrize("val", [0, 1, 8, 2**31, 2**32-1])
def test_log2safe(val: int) -> None:
    val_log = int(math.log2(val)) if val > 0 else 0
    val_ref = min(2**64-1, max(0, val_log))
    assert virtual_pru.log2safe(val) == val_ref


@pytest.mark.parametrize("val", [0, 1, 6, 8, 255, 65000, 2**31, 2**32-1])
def test_get_size_in_bits(val: int) -> None:
    val_log = int(math.log2(val) + 1) if val > 0 else 0
    val_ref = min(2**64-1, max(0, val_log))
    assert virtual_pru.get_size_in_bits(val) == val_ref


@pytest.mark.parametrize("val1", [0, 1, 2**31-1, 2**31, 2**31+1, 2**32-1])
@pytest.mark.parametrize("val2", [0, 1, 2**31-1, 2**31, 2**31+1, 2**32-1])
def test_max_value(val1: int, val2: int) -> None:
    val_ref = max(val1, val2)
    assert virtual_pru.max_value(val1, val2) == val_ref


@pytest.mark.parametrize("val1", [0, 1, 2**31-1, 2**31, 2**31+1, 2**32-1])
@pytest.mark.parametrize("val2", [0, 1, 2**31-1, 2**31, 2**31+1, 2**32-1])
def test_min_value(val1: int, val2: int) -> None:
    val_ref = min(val1, val2)
    assert virtual_pru.min_value(val1, val2) == val_ref