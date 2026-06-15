import pytest
from repartition.core import split


@pytest.mark.eval
def test_eval_3_invalid_parts_zero():
    with pytest.raises(ValueError):
        split(10, 0)


@pytest.mark.eval
def test_eval_3_invalid_parts_negative():
    with pytest.raises(ValueError):
        split(10, -1)


@pytest.mark.eval
def test_eval_3_invalid_total_negative():
    with pytest.raises(ValueError):
        split(-1, 3)


@pytest.mark.eval
def test_eval_3_invalid_total_large_negative():
    with pytest.raises(ValueError):
        split(-100, 5)


@pytest.mark.eval
def test_eval_3_determinism_basic():
    assert split(10, 3) == split(10, 3)


@pytest.mark.eval
def test_eval_3_determinism_zero_total():
    assert split(0, 5) == split(0, 5)


@pytest.mark.eval
def test_eval_3_determinism_single_part():
    assert split(7, 1) == split(7, 1)


@pytest.mark.eval
def test_eval_3_determinism_total_less_than_parts():
    assert split(2, 5) == split(2, 5)
