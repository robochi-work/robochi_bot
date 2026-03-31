from datetime import date, time
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory


class UserFactory(DjangoModelFactory):
    class Meta:
        model = "user.User"

    # Telegram user IDs start from ~100M; sequence ensures uniqueness per test run
    id = factory.Sequence(lambda n: 100_000_000 + n)
    telegram_id = factory.LazyAttribute(lambda o: o.id)
    username = factory.Sequence(lambda n: f"testuser_{n}")
    full_name = factory.Faker("name", locale="uk_UA")
    is_active = True
    is_staff = False


class UserWorkProfileFactory(DjangoModelFactory):
    class Meta:
        model = "work.UserWorkProfile"

    user = factory.SubFactory(UserFactory)
    role = "worker"
    is_completed = True
    agreement_accepted = True


class EmployerFactory(UserFactory):
    """User with an Employer work profile attached."""

    @factory.post_generation
    def _work_profile(self, create, extracted, **kwargs):
        if create:
            UserWorkProfileFactory(
                user=self,
                role="employer",
                is_completed=True,
                agreement_accepted=True,
            )


class WorkerFactory(UserFactory):
    """User with a Worker work profile attached."""

    @factory.post_generation
    def _work_profile(self, create, extracted, **kwargs):
        if create:
            UserWorkProfileFactory(
                user=self,
                role="worker",
                is_completed=True,
                agreement_accepted=True,
            )


class ChannelFactory(DjangoModelFactory):
    class Meta:
        model = "telegram.Channel"

    # Telegram channel IDs are negative
    id = factory.Sequence(lambda n: -1_001_000_000 - n)
    title = factory.Sequence(lambda n: f"Test Channel {n}")
    is_active = True
    has_bot_administrator = True
    invite_link = factory.Sequence(lambda n: f"https://t.me/+channel{n:08d}")


class GroupFactory(DjangoModelFactory):
    class Meta:
        model = "telegram.Group"

    id = factory.Sequence(lambda n: -1_000_000 - n)
    title = factory.Sequence(lambda n: f"Test Group {n}")
    is_active = True
    status = "available"
    invite_link = factory.Sequence(lambda n: f"https://t.me/+group{n:08d}")


class VacancyFactory(DjangoModelFactory):
    class Meta:
        model = "vacancy.Vacancy"

    owner = factory.SubFactory(UserFactory)
    people_count = 2
    has_passport = False
    address = "вул. Хрещатик 1, Київ"
    date = factory.LazyFunction(date.today)
    start_time = factory.LazyFunction(lambda: time(9, 0))
    end_time = factory.LazyFunction(lambda: time(17, 0))
    payment_amount = Decimal("300.00")
    payment_unit = "shift"
    payment_method = "cash"
    skills = "Загальні роботи"
    status = "pending"
