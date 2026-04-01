from typing import Literal

from django.contrib.auth import get_user_model

from vacancy.choices import STATUS_APPROVED, STATUS_REJECTED
from vacancy.models import Vacancy, VacancyStatusHistory
from vacancy.services.observers.events import VACANCY_APPROVED, VACANCY_REJECTED
from vacancy.services.observers.subscriber_setup import vacancy_publisher

User = get_user_model()
Status = Literal["pending", "approved", "rejected"]


def update_vacancy_status(
    vacancy: Vacancy,
    old_status: Status,
    new_status: Status,
    changed_by: User | None = None,
    comment: str | None = None,
) -> None:
    vacancy.status = new_status
    vacancy.save(update_fields=["status"])

    if old_status != new_status:
        VacancyStatusHistory.objects.create(
            vacancy=vacancy, new_status=new_status, changed_by=changed_by, comment=comment
        )
        event = None
        if new_status == STATUS_APPROVED:
            event = VACANCY_APPROVED
        elif new_status == STATUS_REJECTED:
            event = VACANCY_REJECTED

        if event:
            vacancy_publisher.notify(event, data={"vacancy": vacancy})
