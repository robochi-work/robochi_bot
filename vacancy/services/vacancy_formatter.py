from datetime import date
from typing import Literal

from django.utils.translation import gettext as _
from django.utils.translation import override

from user.models import UserFeedback
from vacancy.models import Vacancy


class VacancyTelegramTextFormatter:
    def __init__(self, vacancy: Vacancy):
        self.vacancy = vacancy

    def _get_date_label(self) -> str:
        """Dynamic: if vacancy.date == today -> Сьогодні, else Завтра."""
        with override("uk"):
            if self.vacancy.date == date.today():
                return _("Today")
            else:
                return _("Tomorrow")

    def _get_needed_count(self) -> int:
        """How many workers still needed."""
        current = self.vacancy.members.count()
        needed = self.vacancy.people_count - current
        return max(needed, 0)

    def base_format(self, show_needed: bool = False) -> str:
        with override("uk"):
            date_label = self._get_date_label()
            people_display = self.vacancy.people_count
            if show_needed:
                needed = self._get_needed_count()
                if needed < self.vacancy.people_count:
                    people_display = f"{needed} ({_('of')} {self.vacancy.people_count})"

            return (
                f"{date_label} {self.vacancy.date.strftime('%d.%m.%Y')}\n"
                f"{_('Gender')}: {self.vacancy.get_gender_display()}\n"
                f"{_('Working hours')}: {_('from')} {self.vacancy.start_time.strftime('%H:%M')} {_('to')} {self.vacancy.end_time.strftime('%H:%M')}\n"
                f"{_('Number of People')}: {people_display}\n"
                f'<a href="{self.vacancy.map_link}">{self.vacancy.address}</a>\n\n'
                f"{self.vacancy.skills}\n\n"
                + (f"{_('Need passport')}!\n" if self.vacancy.has_passport else "")
                + f"{_('Payment')}: {int(self.vacancy.payment_amount)} {_('uah')} "
                f"({self.vacancy.get_payment_unit_display()}/{self.vacancy.get_payment_method_display()})\n"
            )

    def for_creator_chat(self) -> str:
        return _("Your request has been created and is being moderated") + "\n" * 2 + self.base_format()

    def for_admin_chat(self) -> str:
        return self.base_format()

    def for_admin_refind(self) -> str:
        return _("Additional search for workers has been launched") + "\n" * 2 + self.base_format()

    def for_admin_new_feedback(self, feedback: UserFeedback) -> str:
        return _("New feedback") + "\n" * 2 + feedback.text

    def for_channel(self, status: Literal["full"] | None = None) -> str:
        if status == "full":
            with override("uk"):
                date_label = self._get_date_label()
                return (
                    f"{date_label} {self.vacancy.date.strftime('%d.%m.%Y')}\n"
                    f"{_('Gender')}: {self.vacancy.get_gender_display()}\n"
                    f"{_('Working hours')}: {_('from')} {self.vacancy.start_time.strftime('%H:%M')} {_('to')} {self.vacancy.end_time.strftime('%H:%M')}\n"
                    f"{_('Number of People')}: {self.vacancy.people_count}\n\n"
                    f"{self.vacancy.skills}\n\n"
                    + (f"{_('Need passport')}!\n" if self.vacancy.has_passport else "")
                    + f"{_('Payment')}: {int(self.vacancy.payment_amount)} {_('uah')} "
                    f"({self.vacancy.get_payment_unit_display()}/{self.vacancy.get_payment_method_display()})\n"
                    + f"{_('Vacancy is close')}"
                )
        else:
            return self.base_format(show_needed=True)

    def for_group(self) -> str:
        return self.base_format()
