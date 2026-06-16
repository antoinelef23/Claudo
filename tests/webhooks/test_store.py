from webhooks.model import PENDING, Delivery
from webhooks.store import DeliveryStore


def test_enqueue_creates_delivery_with_defaults():
    store = DeliveryStore()
    d = store.enqueue("s1", "e1")
    assert isinstance(d, Delivery)
    assert d.sub_id == "s1"
    assert d.event_id == "e1"
    assert d.state == PENDING
    assert d.attempts == 0
    assert d.next_at == 0
    assert d.last_error == ""


def test_enqueue_idempotent_returns_same_object():
    # INV-5 / BHV-5: enqueue twice → same Delivery identity, one entry in store
    store = DeliveryStore()
    d1 = store.enqueue("s1", "e5")
    d2 = store.enqueue("s1", "e5")
    assert d1 is d2


def test_enqueue_idempotent_single_entry_in_store():
    store = DeliveryStore()
    store.enqueue("s1", "e5")
    store.enqueue("s1", "e5")
    assert len(store.all()) == 1


def test_enqueue_different_keys_create_separate_deliveries():
    store = DeliveryStore()
    d1 = store.enqueue("s1", "e1")
    d2 = store.enqueue("s1", "e2")
    d3 = store.enqueue("s2", "e1")
    assert d1 is not d2
    assert d1 is not d3
    assert len(store.all()) == 3


def test_get_returns_delivery_after_enqueue():
    store = DeliveryStore()
    d = store.enqueue("s1", "e1")
    assert store.get("s1", "e1") is d


def test_get_returns_none_for_unknown():
    store = DeliveryStore()
    assert store.get("s1", "e1") is None


def test_get_returns_none_when_wrong_sub():
    store = DeliveryStore()
    store.enqueue("s1", "e1")
    assert store.get("s2", "e1") is None


def test_all_returns_all_enqueued():
    store = DeliveryStore()
    d1 = store.enqueue("s1", "e1")
    d2 = store.enqueue("s1", "e2")
    result = store.all()
    assert set(id(x) for x in result) == {id(d1), id(d2)}


def test_all_empty_initially():
    store = DeliveryStore()
    assert store.all() == []
