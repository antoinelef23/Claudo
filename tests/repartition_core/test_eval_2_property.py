import random

import pytest

from repartition.core import split

_SEED = 20260615
_N = 1000


@pytest.mark.eval
def test_eval_2_property_inv1_sum():
    rng = random.Random(_SEED)
    for _ in range(_N):
        total = rng.randint(0, 10000)
        parts = rng.randint(1, 100)
        shares = split(total, parts)
        assert sum(shares) == total, f"INV-1 violated: sum({shares}) != {total}"


@pytest.mark.eval
def test_eval_2_property_inv2_balance():
    rng = random.Random(_SEED)
    for _ in range(_N):
        total = rng.randint(0, 10000)
        parts = rng.randint(1, 100)
        shares = split(total, parts)
        assert max(shares) - min(shares) <= 1, (
            f"INV-2 violated: max-min > 1 for total={total}, parts={parts}"
        )


@pytest.mark.eval
def test_eval_2_property_inv4_length():
    rng = random.Random(_SEED)
    for _ in range(_N):
        total = rng.randint(0, 10000)
        parts = rng.randint(1, 100)
        shares = split(total, parts)
        assert len(shares) == parts, (
            f"INV-4 violated: len={len(shares)} != parts={parts}"
        )


@pytest.mark.eval
def test_eval_2_property_int_types():
    rng = random.Random(_SEED)
    for _ in range(_N):
        total = rng.randint(0, 10000)
        parts = rng.randint(1, 100)
        shares = split(total, parts)
        for v in shares:
            assert isinstance(v, int), (
                f"element {v!r} is not int (total={total}, parts={parts})"
            )
