from webhooks.transport import FakeTransport, Transport


def test_fake_transport_returns_results_in_order():
    t = FakeTransport([True, False, True])
    assert t.send("http://a", "{}", "sig1") is True
    assert t.send("http://a", "{}", "sig2") is False
    assert t.send("http://a", "{}", "sig3") is True


def test_fake_transport_records_calls():
    t = FakeTransport([True, False])
    t.send("http://a/hook", '{"k":"v"}', "abc123")
    t.send("http://b/hook", "{}", "def456")
    assert len(t.calls) == 2
    assert t.calls[0] == ("http://a/hook", '{"k":"v"}', "abc123")
    assert t.calls[1] == ("http://b/hook", "{}", "def456")


def test_fake_transport_exhausted_returns_false():
    t = FakeTransport([True])
    t.send("http://a", "{}", "s")  # consumes the single result
    # results exhausted → False, no IndexError
    assert t.send("http://a", "{}", "s") is False
    assert t.send("http://a", "{}", "s") is False


def test_fake_transport_empty_results_always_false():
    t = FakeTransport([])
    assert t.send("http://a", "{}", "s") is False


def test_fake_transport_calls_initially_empty():
    t = FakeTransport([True])
    assert t.calls == []


def test_fake_transport_calls_accumulate_across_all_sends():
    t = FakeTransport([True, False, False])
    for i in range(3):
        t.send(f"http://url-{i}", f"payload-{i}", f"sig-{i}")
    assert len(t.calls) == 3
    assert t.calls[2] == ("http://url-2", "payload-2", "sig-2")


def test_fake_transport_satisfies_transport_protocol():
    # Protocol structural check: FakeTransport must have a compatible send method
    t: Transport = FakeTransport([True])
    result = t.send("http://a", "{}", "sig")
    assert result is True
