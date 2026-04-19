from types import SimpleNamespace

from user.models import User

from .notifications import NotificationMethod
from .notifications_impl import TelegramNotifier


class TelegramBroadcastService:
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def broadcast(self, chat_ids: list[int], method: NotificationMethod, **kwargs) -> None:
        for chat_id in chat_ids:
            recipient = SimpleNamespace(chat_id=chat_id)
            self.notifier.notify(recipient, method, **kwargs)

    def admin_broadcast(self, method: NotificationMethod = NotificationMethod.TEXT, **kwargs) -> None:
        ids = User.objects.filter(is_staff=True).values_list("id", flat=True)
        self.broadcast(chat_ids=ids, method=method, **kwargs)
