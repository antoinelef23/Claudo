from webhooks.engine import deliver
from webhooks.model import DEAD_LETTER, DELIVERED, Event, Subscription
from webhooks.store import DeliveryStore
from webhooks.transport import FakeTransport


def _clock(start: int = 0, step: int = 1000):
    val = [start]

    def clock() -> int:
        v = val[0]
        val[0] += step
        return v

    return clock


def _sub(max_attempts: int = 5) -> Subscription:
    return Subscription(
        id="s1",
        url="https://example.com/hook",
        secret="secret",
        max_attempts=max_attempts,
    )


def test_bhv1_success_first_attempt():
    event = Event(id="e1", payload="{}")
    store = DeliveryStore()
    transport = FakeTransport([True])

    delivery = deliver(store, transport, _sub(), event, _clock())

    assert delivery.state == DELIVERED
    assert len(transport.calls) == 1


def test_bhv2_fail_then_success():
    event = Event(id="e1", payload="{}")
    store = DeliveryStore()
    transport = FakeTransport([False, True])

    delivery = deliver(store, transport, _sub(max_attempts=5), event, _clock())

    assert delivery.state == DELIVERED
    assert len(transport.calls) == 2
    assert delivery.next_at > 0


def test_bhv3_all_fail_dead_letter():
    event = Event(id="e1", payload="{}")
    store = DeliveryStore()
    transport = FakeTransport([False, False, False])

    delivery = deliver(store, transport, _sub(max_attempts=3), event, _clock())

    assert delivery.state == DEAD_LETTER
    assert len(transport.calls) == 3
    assert delivery.last_error != ""
    assert delivery.attempts == 3
