"""EVAL-1 — EX-1..EX-5 de spec.md §6 vérifiés exactement (100 %).

Couvre : BHV-1 (EX-1), BHV-2 (EX-2), BHV-3 (EX-3), BHV-4/BHV-4a (EX-4), BHV-5 (EX-5).
Contexte par défaut spec §6 : base_ms=1000, cap_ms=60000,
horloge logique partant de 0 puis +1000 par appel.
Aucun réseau / aléa / now() (INV-7).
"""

import pytest

from webhooks.engine import deliver
from webhooks.model import DEAD_LETTER, DELIVERED, Event, Subscription, backoff_ms
from webhooks.store import DeliveryStore
from webhooks.transport import FakeTransport


def _clock(start: int = 0, step: int = 1000):
    state = [start]

    def _tick() -> int:
        val = state[0]
        state[0] += step
        return val

    return _tick


@pytest.mark.eval
def test_eval_1_ex1_immediate_success():
    """EX-1 — BHV-1 : succès immédiat → DELIVERED, exactement 1 appel de transport."""
    sub = Subscription(id="s1", url="https://a/hook", secret="k", max_attempts=5)
    evt = Event(id="e1", payload="{}")
    transport = FakeTransport(results=[True])
    store = DeliveryStore()

    delivery = deliver(store, transport, sub, evt, _clock(), base_ms=1000, cap_ms=60000)

    assert delivery.state == DELIVERED
    assert len(transport.calls) == 1


@pytest.mark.eval
def test_eval_1_ex2_failure_then_success():
    """EX-2 — BHV-2 : 1 échec puis 1 succès → DELIVERED, exactement 2 appels."""
    sub = Subscription(id="s1", url="https://a/hook", secret="k", max_attempts=5)
    evt = Event(id="e2", payload="{}")
    transport = FakeTransport(results=[False, True])
    store = DeliveryStore()

    delivery = deliver(store, transport, sub, evt, _clock(), base_ms=1000, cap_ms=60000)

    assert delivery.state == DELIVERED
    assert len(transport.calls) == 2


@pytest.mark.eval
def test_eval_1_ex3_dead_letter_after_max_attempts():
    """EX-3 — BHV-3 : toujours échec, max_attempts=3 → DEAD_LETTER, 3 appels, last_error renseigné."""
    sub = Subscription(id="s1", url="https://a/hook", secret="k", max_attempts=3)
    evt = Event(id="e3", payload="{}")
    transport = FakeTransport(results=[False, False, False])
    store = DeliveryStore()

    delivery = deliver(store, transport, sub, evt, _clock(), base_ms=1000, cap_ms=60000)

    assert delivery.state == DEAD_LETTER
    assert len(transport.calls) == 3
    assert delivery.last_error != ""


@pytest.mark.eval
def test_eval_1_ex4_backoff_series():
    """EX-4 — BHV-4/BHV-4a : barème n=[1,2,3,7,20] base=1000 cap=60000 → [1000,2000,4000,60000,60000]."""
    ns = [1, 2, 3, 7, 20]
    expected = [1000, 2000, 4000, 60000, 60000]

    result = [backoff_ms(n, base_ms=1000, cap_ms=60000) for n in ns]

    assert result == expected


@pytest.mark.eval
def test_eval_1_ex5_enqueue_idempotent():
    """EX-5 — BHV-5 : enqueue deux fois le même (sub_id, event_id) → 1 seule delivery en store."""
    sub = Subscription(id="s1", url="https://a/hook", secret="k", max_attempts=5)
    evt = Event(id="e5", payload="{}")
    store = DeliveryStore()

    d1 = store.enqueue(sub.id, evt.id)
    d2 = store.enqueue(sub.id, evt.id)

    assert len(store.all()) == 1
    assert d1 is d2
