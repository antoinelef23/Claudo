from dataclasses import dataclass

MAX_SKEW = 300  # seconds — anti-replay window (INV-3)


@dataclass(frozen=True)
class WebhookEvent:
    event_id: str
    type: str
    data: dict
