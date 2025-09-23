from typing import Any
from telegram.handlers.messages.commands import default_start
from vacancy.services.observers.publisher import Observer

class UserWorkProfileCompleteObserver(Observer):

    def update(self, event: str, data: dict[str, Any]) -> None:
        user = data.get('user')
        if user:
            default_start(None, user=user)

