import pytest
from dataclasses import FrozenInstanceError
from webhooks.model import (
    PENDING,
    DELIVERED,
    DEAD_LETTER,
    Subscription,
    Event,
    Delivery,
    backoff_ms,
)


# --- constants ---


def test_state_constants():
    assert PENDING == "PENDING"
    assert DELIVERED == "DELIVERED"
    assert DEAD_LETTER == "DEAD_LETTER"


# --- Subscription ---


def test_subscription_fields():
    s = Subscription(id="s1", url="https://a/hook", secret="k", max_attempts=3)
    assert s.id == "s1"
    assert s.url == "https://a/hook"
    assert s.secret == "k"
    assert s.max_attempts == 3


def test_subscription_is_frozen():
    s = Subscription(id="s1", url="https://a/hook", secret="k", max_attempts=3)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        s.id = "x"  # type: ignore[misc]


def test_subscription_max_attempts_minimum_valid():
    s = Subscription(id="s1", url="u", secret="k", max_attempts=1)
    assert s.max_attempts == 1


def test_subscription_max_attempts_zero_raises():
    with pytest.raises(ValueError):
        Subscription(id="s1", url="u", secret="k", max_attempts=0)


def test_subscription_max_attempts_negative_raises():
    with pytest.raises(ValueError):
        Subscription(id="s1", url="u", secret="k", max_attempts=-1)


# --- Event ---


def test_event_fields():
    e = Event(id="e1", payload="{}")
    assert e.id == "e1"
    assert e.payload == "{}"


def test_event_is_frozen():
    e = Event(id="e1", payload="{}")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        e.id = "x"  # type: ignore[misc]


# --- Delivery ---


def test_delivery_fields():
    d = Delivery(
        sub_id="s1", event_id="e1", state=PENDING, attempts=0, next_at=0, last_error=""
    )
    assert d.sub_id == "s1"
    assert d.event_id == "e1"
    assert d.state == PENDING
    assert d.attempts == 0
    assert d.next_at == 0
    assert d.last_error == ""


def test_delivery_is_mutable():
    d = Delivery(
        sub_id="s1", event_id="e1", state=PENDING, attempts=0, next_at=0, last_error=""
    )
    d.state = DELIVERED
    assert d.state == DELIVERED


# --- backoff_ms (INV-3, BHV-4, BHV-4a) ---


def test_backoff_attempt_1_equals_base():
    assert backoff_ms(1, base_ms=1000, cap_ms=60000) == 1000


def test_backoff_attempt_2_doubles():
    assert backoff_ms(2, base_ms=1000, cap_ms=60000) == 2000


def test_backoff_attempt_3_quadruples():
    assert backoff_ms(3, base_ms=1000, cap_ms=60000) == 4000


def test_backoff_series_from_spec_ex4():
    # EX-4: n=[1,2,3,7,20] base=1000 cap=60000 -> [1000,2000,4000,60000,60000]
    inputs = [1, 2, 3, 7, 20]
    expected = [1000, 2000, 4000, 60000, 60000]
    results = [backoff_ms(n, base_ms=1000, cap_ms=60000) for n in inputs]
    assert results == expected


def test_backoff_capped_at_cap_ms():
    # 2^6 * 1000 = 64000 > 60000 -> should return 60000
    assert backoff_ms(7, base_ms=1000, cap_ms=60000) == 60000


def test_backoff_non_decreasing(benchmark_series=None):
    # INV-3: non-décroissant — vérifié sur 30 tentatives
    base, cap = 500, 30000
    values = [backoff_ms(n, base_ms=base, cap_ms=cap) for n in range(1, 31)]
    for i in range(len(values) - 1):
        assert values[i] <= values[i + 1], f"backoff decreased at attempt {i + 2}"


def test_backoff_never_exceeds_cap():
    base, cap = 1000, 60000
    for n in range(1, 25):
        assert backoff_ms(n, base_ms=base, cap_ms=cap) <= cap


def test_backoff_exact_cap_boundary():
    # min(1000 * 2^(6-1), 60000) = min(32000, 60000) = 32000 (not capped)
    assert backoff_ms(6, base_ms=1000, cap_ms=60000) == 32000
    # min(1000 * 2^(7-1), 60000) = min(64000, 60000) = 60000 (capped)
    assert backoff_ms(7, base_ms=1000, cap_ms=60000) == 60000


def test_backoff_small_base():
    assert backoff_ms(1, base_ms=100, cap_ms=10000) == 100
    assert backoff_ms(4, base_ms=100, cap_ms=10000) == 800
    assert backoff_ms(8, base_ms=100, cap_ms=10000) == 10000  # 100*128=12800 -> capped


def test_backoff_cap_equals_base():
    # When cap == base, all attempts return base
    for n in range(1, 6):
        assert backoff_ms(n, base_ms=500, cap_ms=500) == 500
