from abc import ABC, abstractmethod
from typing import Any

class Observer(ABC):
    @abstractmethod
    def update(self, event: str, data: dict[str, Any]) -> None:
        raise NotImplementedError()

class BasePublisher:

    def __init__(self):
        self._subscribers: dict[str, list[Observer]] = {}

    def subscribe(self, event: str, observer: Observer) -> None:
        self._subscribers.setdefault(event, []).append(observer)

    def unsubscribe(self, event: str, observer: Observer) -> None:
        if event in self._subscribers:
            self._subscribers[event].remove(observer)

    def notify(self, event: str, data: dict[str, Any]) -> None:
        for observer in self._subscribers.get(event, []):
            observer.update(event, data)

class VacancyEventPublisher(BasePublisher):
    ...