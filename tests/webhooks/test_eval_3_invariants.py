import pytest

from webhooks.engine import deliver
from webhooks.model import DELIVERED, Event, Subscription, backoff_ms
from webhooks.signing import sign
from webhooks.store import DeliveryStore
from webhooks.transport import FakeTransport


def _clock(start: int = 0, step: int = 1000):
    val = [start]

    def clock() -> int:
        v = val[0]
        val[0] += step
        return v

    return clock


@pytest.mark.eval
def test_eval_3_invariants():
    # INV-3: backoff croissant et capé
    base_ms, cap_ms = 1000, 60_000
    series = [backoff_ms(n, base_ms, cap_ms) for n in range(1, 25)]
    assert series[0] == base_ms
    for idx in range(len(series) - 1):
        assert series[idx] <= series[idx + 1], (
            f"backoff non-monotone à n={idx + 1}: {series[idx]} > {series[idx + 1]}"
        )
    assert all(v <= cap_ms for v in series), "backoff dépasse cap_ms"

    # INV-6: signature déterministe — même entrée → même sortie
    assert sign("secret", '{"foo": "bar"}') == sign("secret", '{"foo": "bar"}')

    # INV-6 via engine : deux tentatives sur le même (secret, payload) produisent la même signature
    sub_sig = Subscription(id="sig", url="https://h/hook", secret="key", max_attempts=3)
    event_sig = Event(id="esig", payload='{"x": 1}')
    store_sig = DeliveryStore()
    transport_sig = FakeTransport([False, True])
    deliver(store_sig, transport_sig, sub_sig, event_sig, _clock())
    assert len(transport_sig.calls) == 2
    assert transport_sig.calls[0][2] == transport_sig.calls[1][2], (
        "signatures différentes entre tentatives (INV-6)"
    )

    # BHV-7: re-livraison d'un DELIVERED = no-op (INV-1)
    sub_noop = Subscription(
        id="noop", url="https://h/hook", secret="secret", max_attempts=5
    )
    event_noop = Event(id="enoop", payload="{}")
    store_noop = DeliveryStore()
    transport_noop = FakeTransport([True])
    delivery_noop = deliver(store_noop, transport_noop, sub_noop, event_noop, _clock())
    assert delivery_noop.state == DELIVERED
    assert len(transport_noop.calls) == 1
    deliver(store_noop, transport_noop, sub_noop, event_noop, _clock())
    assert len(transport_noop.calls) == 1, "send appelé après DELIVERED (BHV-7/INV-1)"

    # INV-5: enqueue idempotent
    store_idem = DeliveryStore()
    sub_idem = Subscription(
        id="idem", url="https://h/hook", secret="secret", max_attempts=5
    )
    event_idem = Event(id="eidem", payload="{}")
    d1 = store_idem.enqueue(sub_idem.id, event_idem.id)
    d2 = store_idem.enqueue(sub_idem.id, event_idem.id)
    assert d1 is d2, (
        "enqueue a renvoyé deux objets distincts pour (sub_id, event_id) identiques (INV-5)"
    )
    assert len(store_idem.all()) == 1, (
        "store contient plus d'une delivery pour (sub_id, event_id) identiques (INV-5)"
    )
