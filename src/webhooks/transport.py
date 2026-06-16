from typing import Protocol


class Transport(Protocol):
    def send(self, url: str, payload: str, signature: str) -> bool: ...


class FakeTransport:
    def __init__(self, results: list[bool]) -> None:
        self._results = list(results)
        self._index = 0
        self.calls: list[tuple[str, str, str]] = []

    def send(self, url: str, payload: str, signature: str) -> bool:
        self.calls.append((url, payload, signature))
        if self._index < len(self._results):
            result = self._results[self._index]
            self._index += 1
            return result
        return False
