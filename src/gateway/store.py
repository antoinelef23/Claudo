from typing import Protocol


class EventStore(Protocol):
    def add_if_absent(self, event_id: str, payload: dict) -> bool: ...
    def get(self, event_id: str) -> dict | None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def add_if_absent(self, event_id: str, payload: dict) -> bool:
        if event_id in self._store:
            return False
        self._store[event_id] = payload
        return True

    def get(self, event_id: str) -> dict | None:
        return self._store.get(event_id)
