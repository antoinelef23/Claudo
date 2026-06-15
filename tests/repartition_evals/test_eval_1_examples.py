import pytest

from repartition.core import split


@pytest.mark.eval
def test_eval_1_ex1_division_exacte():
    assert split(9, 3) == [3, 3, 3]


@pytest.mark.eval
def test_eval_1_ex2_reste_distribue():
    assert split(10, 3) == [4, 3, 3]


@pytest.mark.eval
def test_eval_1_ex3_reste_de_1_sur_2_parts():
    assert split(7, 2) == [4, 3]


@pytest.mark.eval
def test_eval_1_ex4_plus_de_parts_que_unites():
    assert split(2, 5) == [1, 1, 0, 0, 0]


@pytest.mark.eval
def test_eval_1_ex5_total_nul():
    assert split(0, 3) == [0, 0, 0]
