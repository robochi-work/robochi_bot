from abc import ABC, abstractmethod
from django.core.handlers.wsgi import WSGIRequest


class PageBlock(ABC):
    order = 0

    @abstractmethod
    def is_visible(self, request: WSGIRequest) -> bool:
        ...

    @abstractmethod
    def get_context(self, request: WSGIRequest) -> dict:
        ...

    @property
    def template_name(self):
        raise NotImplementedError()