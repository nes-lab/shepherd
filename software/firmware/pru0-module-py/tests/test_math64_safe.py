import math

import pytest
from shepherd_pru._virtual_pru import virtual_pru

val_u32a = [0, 1, 2, 6, 8, 255, 65000]
val_u32b = [2**16 - 1, 2**16, 2**16 + 1]
val_u32c = [2**31 - 1, 2**31, 2**31 + 1]
val_u32d = [2**32 - 1]
val_u32 = [*val_u32a, *val_u32b, *val_u32c, *val_u32d]
val_u64 = [2**32, 2**32 + 1, 2**63 - 1, 2**63, 2**63 + 1, 2**64 - 1]
val_i32 = [-_i for _i in val_u32 if _i < 2**31] + [_i for _i in val_u32 if _i < 2**31]


def get_size_in_bits(val: int) -> int:
    val_ = val
    counter: int = 0
    while val_ >= 1:
        counter += 1
        val_ = val_ // 2
    return counter


@pytest.mark.parametrize("val1", val_u32)
@pytest.mark.parametrize("val2", val_u32)
def test_mul32(val1: int, val2: int) -> None:
    val_ref = min(2**32 - 1, max(0, val1 * val2))
    assert virtual_pru.mul32(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32 + val_u64)
@pytest.mark.parametrize("val2", val_u32 + val_u64)
def test_mul64(val1: int, val2: int) -> None:
    # 1 * 9223372036854775808
    # 2147483647 * 4294967296
    if get_size_in_bits(val1) + get_size_in_bits(val2) <= 64:
        val_ref = min(2**64 - 1, max(0, val1 * val2))
    else:
        # pru takes a shortcut -> incorrect for numbers near u64-max
        val_ref = 2**64 - 1
    assert virtual_pru.mul64(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32)
@pytest.mark.parametrize("val2", val_u32)
def test_add32(val1: int, val2: int) -> None:
    val_ref = min(2**32 - 1, max(0, val1 + val2))
    assert virtual_pru.add32(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32 + val_u64)
@pytest.mark.parametrize("val2", val_u32 + val_u64)
def test_add64(val1: int, val2: int) -> None:
    val_ref = min(2**64 - 1, max(0, val1 + val2))
    assert virtual_pru.add64(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32)
@pytest.mark.parametrize("val2", val_i32)
def test_add32s(val1: int, val2: int) -> None:
    val_ref = min(2**32 - 1, max(0, val1 + val2))
    assert virtual_pru.add32s(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32)
@pytest.mark.parametrize("val2", val_u32)
def test_sub32(val1: int, val2: int) -> None:
    val_ref = min(2**32 - 1, max(0, val1 - val2))
    assert virtual_pru.sub32(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32 + val_u64)
@pytest.mark.parametrize("val2", val_u32 + val_u64)
def test_sub64(val1: int, val2: int) -> None:
    val_ref = min(2**64 - 1, max(0, val1 - val2))
    assert virtual_pru.sub64(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32)
@pytest.mark.parametrize("val2", val_i32)
def test_sub32s(val1: int, val2: int) -> None:
    val_ref = min(2**32 - 1, max(0, val1 - val2))
    assert virtual_pru.sub32s(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32)
@pytest.mark.parametrize("val2", val_u32)
def test_abs_delta32(val1: int, val2: int) -> None:
    val_ref = val1 - val2 if val1 > val2 else val2 - val1
    assert virtual_pru.abs_delta32(val1, val2) == val_ref


@pytest.mark.parametrize("val", val_u32)
def test_log2safe(val: int) -> None:
    val_log = int(math.log2(val)) if val > 0 else 0
    val_ref = min(2**64 - 1, max(0, val_log))
    assert virtual_pru.log2safe(val) == val_ref


@pytest.mark.parametrize("val", val_u32)
def test_get_size_in_bits(val: int) -> None:
    val_log = int(math.log2(val) + 1) if val > 0 else 0
    val_ref1 = min(2**64 - 1, max(0, val_log))
    val_ref2 = get_size_in_bits(val)
    assert virtual_pru.get_size_in_bits(val) == val_ref1
    assert virtual_pru.get_size_in_bits(val) == val_ref2


@pytest.mark.parametrize("val1", val_u32)
@pytest.mark.parametrize("val2", val_u32)
def test_max_value(val1: int, val2: int) -> None:
    val_ref = max(val1, val2)
    assert virtual_pru.max_value(val1, val2) == val_ref


@pytest.mark.parametrize("val1", val_u32)
@pytest.mark.parametrize("val2", val_u32)
def test_min_value(val1: int, val2: int) -> None:
    val_ref = min(val1, val2)
    assert virtual_pru.min_value(val1, val2) == val_ref
