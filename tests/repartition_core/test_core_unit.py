import pytest
from repartition.core import split


# BHV-1 — exact division
def test_exact_division():
    assert split(9, 3) == [3, 3, 3]


# BHV-2 — remainder distributed to first parts
def test_remainder_one():
    assert split(7, 2) == [4, 3]


def test_remainder_many():
    assert split(10, 3) == [4, 3, 3]


# BHV-3 — more parts than units
def test_more_parts_than_total():
    assert split(2, 5) == [1, 1, 0, 0, 0]


def test_total_one_many_parts():
    assert split(1, 4) == [1, 0, 0, 0]


# BHV-3a — total == 0
def test_total_zero():
    assert split(0, 3) == [0, 0, 0]


def test_total_zero_one_part():
    assert split(0, 1) == [0]


# BHV-1 edge — single part
def test_single_part():
    assert split(42, 1) == [42]


# INV-4 — len == parts
def test_length_equals_parts():
    for total, parts in [(0, 1), (10, 3), (100, 7), (1, 1)]:
        assert len(split(total, parts)) == parts


# INV-1 — sum == total
def test_sum_equals_total():
    for total, parts in [(0, 1), (10, 3), (100, 7), (7, 2), (2, 5)]:
        assert sum(split(total, parts)) == total


# INV-2 — max - min <= 1
def test_balance():
    for total, parts in [(10, 3), (100, 7), (7, 2), (2, 5), (1000, 99)]:
        shares = split(total, parts)
        assert max(shares) - min(shares) <= 1


# BHV-4 — ValueError on invalid inputs
def test_parts_zero_raises():
    with pytest.raises(ValueError):
        split(10, 0)


def test_parts_negative_raises():
    with pytest.raises(ValueError):
        split(10, -1)


def test_total_negative_raises():
    with pytest.raises(ValueError):
        split(-1, 3)


def test_both_invalid_raises():
    with pytest.raises(ValueError):
        split(-5, -2)
