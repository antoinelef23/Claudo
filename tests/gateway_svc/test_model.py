import pytest
from dataclasses import FrozenInstanceError

from gateway.model import WebhookEvent, MAX_SKEW


def test_webhook_event_fields():
    event = WebhookEvent(event_id="e1", type="order.created", data={"amount": 42})
    assert event.event_id == "e1"
    assert event.type == "order.created"
    assert event.data == {"amount": 42}


def test_webhook_event_frozen():
    event = WebhookEvent(event_id="e1", type="order.created", data={"amount": 42})
    with pytest.raises(FrozenInstanceError):
        event.event_id = "other"  # type: ignore[misc]


def test_max_skew_value():
    assert MAX_SKEW == 300
