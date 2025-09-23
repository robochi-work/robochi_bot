from .notifications import NotificationMethod
from .telegram_strategies import TextStrategy, PhotoStrategy, InvoiceStrategy


class TelegramStrategyFactory:
    _registry = {
        NotificationMethod.TEXT: TextStrategy(),
        NotificationMethod.PHOTO: PhotoStrategy(),
        NotificationMethod.INVOICE: InvoiceStrategy(),
    }

    @classmethod
    def get_strategy(cls, method: NotificationMethod):
        strategy = cls._registry.get(method)
        if not strategy:
            raise ValueError(f'No strategy registered for {method}')
        return strategy

    @classmethod
    def register_strategy(cls, method: NotificationMethod, strategy):
        cls._registry[method] = strategy
