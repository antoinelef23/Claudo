from dataclasses import dataclass

PENDING = "PENDING"
DELIVERED = "DELIVERED"
DEAD_LETTER = "DEAD_LETTER"


@dataclass(frozen=True)
class Subscription:
    id: str
    url: str
    secret: str
    max_attempts: int

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")


@dataclass(frozen=True)
class Event:
    id: str
    payload: str


@dataclass
class Delivery:
    sub_id: str
    event_id: str
    state: str
    attempts: int
    next_at: int
    last_error: str


def backoff_ms(attempt: int, base_ms: int, cap_ms: int) -> int:
    return min(base_ms * (2 ** (attempt - 1)), cap_ms)
