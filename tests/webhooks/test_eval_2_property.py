import random

import pytest

from webhooks.engine import deliver
from webhooks.model import DEAD_LETTER, DELIVERED, Event, Subscription
from webhooks.store import DeliveryStore
from webhooks.transport import FakeTransport

SEED = 42


def _make_clock():
    val = [0]

    def clock() -> int:
        v = val[0]
        val[0] += 1000
        return v

    return clock


@pytest.mark.eval
def test_eval_2_property():
    rng = random.Random(SEED)

    for i in range(1000):
        max_attempts = rng.randint(1, 10)
        results = [rng.random() < 0.5 for _ in range(max_attempts)]

        sub = Subscription(
            id=f"s{i}",
            url="https://example.com/hook",
            secret="secret",
            max_attempts=max_attempts,
        )
        event = Event(id=f"e{i}", payload="{}")
        store = DeliveryStore()
        transport = FakeTransport(results)
        clock = _make_clock()

        delivery = deliver(store, transport, sub, event, clock)

        calls_count = len(transport.calls)

        # INV-2: appels <= max_attempts
        assert calls_count <= max_attempts, (
            f"scenario {i}: {calls_count} calls > {max_attempts} max_attempts"
        )

        # INV-1(a): au plus 1 succès dans les appels consommés
        consumed = results[:calls_count]
        success_count = sum(1 for r in consumed if r)
        assert success_count <= 1, (
            f"scenario {i}: {success_count} successes in consumed calls"
        )

        # état terminal
        assert delivery.state in (DELIVERED, DEAD_LETTER), (
            f"scenario {i}: non-terminal state {delivery.state!r}"
        )

        # INV-4: DEAD_LETTER → tous les max_attempts utilisés
        if delivery.state == DEAD_LETTER:
            assert calls_count == max_attempts, (
                f"scenario {i}: DEAD_LETTER with {calls_count} calls, expected {max_attempts}"
            )

        # INV-1(b): aucun send après DELIVERED
        if delivery.state == DELIVERED:
            deliver(store, transport, sub, event, clock)
            assert len(transport.calls) == calls_count, (
                f"scenario {i}: send called after DELIVERED"
            )
