import logging
from typing import Any

from vacancy.services.observers.publisher import Observer

logger = logging.getLogger(__name__)


class UserWorkProfileCompleteObserver(Observer):
    """
    Called after wizard completion. Currently a no-op.
    In the future this could trigger notifications, channel subscriptions, etc.
    """

    def update(self, event: str, data: dict[str, Any]) -> None:
        user = data.get("user")
        if user:
            logger.info(f"Work profile completed for user {user.id}")
