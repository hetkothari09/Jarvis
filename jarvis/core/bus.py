"""In-process publish/subscribe event bus. No threads, synchronous delivery."""
from collections import defaultdict
from typing import Any, Callable


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> Callable[[], None]:
        self._subs[topic].append(handler)

        def unsubscribe() -> None:
            if handler in self._subs[topic]:
                self._subs[topic].remove(handler)

        return unsubscribe

    def publish(self, topic: str, payload: Any = None) -> None:
        for handler in list(self._subs[topic]):
            try:
                handler(payload)
            except Exception:
                # One bad subscriber must not break others or the publisher.
                pass
