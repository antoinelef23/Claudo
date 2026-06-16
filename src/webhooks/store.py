from webhooks.model import PENDING, Delivery


class DeliveryStore:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Delivery] = {}

    def enqueue(self, sub_id: str, event_id: str) -> Delivery:
        key = (sub_id, event_id)
        if key not in self._store:
            self._store[key] = Delivery(
                sub_id=sub_id,
                event_id=event_id,
                state=PENDING,
                attempts=0,
                next_at=0,
                last_error="",
            )
        return self._store[key]

    def get(self, sub_id: str, event_id: str) -> Delivery | None:
        return self._store.get((sub_id, event_id))

    def all(self) -> list[Delivery]:
        return list(self._store.values())
