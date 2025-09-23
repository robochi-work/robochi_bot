from abc import ABC, abstractmethod
from enum import Enum, auto


class NotificationMethod(Enum):
    TEXT = auto()
    PHOTO = auto()
    INVOICE = auto()


class Notifier(ABC):
    @abstractmethod
    def notify(self, recipient: object, method: NotificationMethod, **kwargs) -> None:
        pass
