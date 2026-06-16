from gateway.store import EventStore, InMemoryStore


def test_add_new_event_returns_true():
    store = InMemoryStore()
    result = store.add_if_absent("evt-1", {"type": "payment", "data": {}})
    assert result is True


def test_get_returns_payload_after_add():
    store = InMemoryStore()
    payload = {"type": "payment", "data": {"amount": 42}}
    store.add_if_absent("evt-1", payload)
    assert store.get("evt-1") == payload


def test_readd_same_id_returns_false():
    store = InMemoryStore()
    payload = {"type": "payment", "data": {}}
    store.add_if_absent("evt-1", payload)
    result = store.add_if_absent("evt-1", {"type": "other", "data": {}})
    assert result is False


def test_readd_does_not_modify_store():
    store = InMemoryStore()
    original = {"type": "payment", "data": {"amount": 10}}
    store.add_if_absent("evt-1", original)
    store.add_if_absent("evt-1", {"type": "overwrite", "data": {"amount": 999}})
    assert store.get("evt-1") == original


def test_get_unknown_id_returns_none():
    store = InMemoryStore()
    assert store.get("does-not-exist") is None


def test_independent_ids_are_stored_separately():
    store = InMemoryStore()
    p1 = {"type": "a", "data": {}}
    p2 = {"type": "b", "data": {}}
    assert store.add_if_absent("evt-1", p1) is True
    assert store.add_if_absent("evt-2", p2) is True
    assert store.get("evt-1") == p1
    assert store.get("evt-2") == p2


def test_in_memory_store_satisfies_event_store_protocol():
    store: EventStore = InMemoryStore()
    assert store.add_if_absent("x", {}) is True
    assert store.get("x") == {}
