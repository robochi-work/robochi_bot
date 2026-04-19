"""
Tests for the observer / pub-sub subscription setup.

These tests verify that:
1. Both subscriber_setup modules import without raising exceptions.
2. After import, the vacancy publisher has subscribers registered for
   the critical events we depend on in production.

The autouse mock_bot_api fixture (conftest.py) ensures the TeleBot
instance used inside subscriber_setup never makes real API calls.
"""

import pytest


@pytest.mark.django_db
def test_vacancy_subscriber_setup_imports_cleanly():
    """Importing subscriber_setup must not raise any exception."""
    # Re-import forces execution of module-level subscription code.
    # If any observer class is missing or mis-configured this will blow up.
    import importlib
    import sys

    mod_name = "vacancy.services.observers.subscriber_setup"
    sys.modules.pop(mod_name, None)

    module = importlib.import_module(mod_name)
    assert module is not None


@pytest.mark.django_db
def test_work_subscriber_setup_imports_cleanly():
    """work.service.subscriber_setup must import without raising."""
    import importlib
    import sys

    mod_name = "work.service.subscriber_setup"
    sys.modules.pop(mod_name, None)

    module = importlib.import_module(mod_name)
    assert module is not None


@pytest.mark.django_db
def test_vacancy_publisher_has_created_subscribers():
    """VACANCY_CREATED event must have at least two subscribers (user + admin)."""
    from vacancy.services.observers import subscriber_setup
    from vacancy.services.observers.events import VACANCY_CREATED

    publisher = subscriber_setup.vacancy_publisher
    # BasePublisher stores subscribers in a dict keyed by event string
    subscribers = publisher._subscribers.get(VACANCY_CREATED, [])
    assert len(subscribers) >= 2, f"Expected >= 2 subscribers for VACANCY_CREATED, got {len(subscribers)}"


@pytest.mark.django_db
def test_vacancy_publisher_has_close_subscribers():
    """VACANCY_CLOSE event must have subscribers (status, messages, kick, etc.)."""
    from vacancy.services.observers import subscriber_setup
    from vacancy.services.observers.events import VACANCY_CLOSE

    publisher = subscriber_setup.vacancy_publisher
    subscribers = publisher._subscribers.get(VACANCY_CLOSE, [])
    assert len(subscribers) >= 3, f"Expected >= 3 subscribers for VACANCY_CLOSE, got {len(subscribers)}"


@pytest.mark.django_db
def test_vacancy_publisher_has_approved_subscribers():
    """VACANCY_APPROVED event must have subscribers (user, channel, group)."""
    from vacancy.services.observers import subscriber_setup
    from vacancy.services.observers.events import VACANCY_APPROVED

    publisher = subscriber_setup.vacancy_publisher
    subscribers = publisher._subscribers.get(VACANCY_APPROVED, [])
    assert len(subscribers) >= 3, f"Expected >= 3 subscribers for VACANCY_APPROVED, got {len(subscribers)}"
