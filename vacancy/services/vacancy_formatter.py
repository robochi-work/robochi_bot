from typing import Literal, Optional

from django.utils.translation import gettext as _, override

from user.models import UserFeedback
from vacancy.models import Vacancy


class VacancyTelegramTextFormatter:

    def __init__(self, vacancy: Vacancy):
        self.vacancy = vacancy

    def base_format(self) -> str:
        with override('uk'):
            return (
                f"{self.vacancy.get_date_choice_display()} {self.vacancy.date.strftime('%d.%m.%Y')}\n"
                f"{_('Sex')}: {self.vacancy.get_gender_display()}\n"
                f"{_('Work time')}: {_('from')} {self.vacancy.start_time.strftime('%H:%M')} {_('to')} {self.vacancy.end_time.strftime('%H:%M')}\n"
                f"{_('Number of People')}: {self.vacancy.people_count}\n"
                f"<a href=\"{self.vacancy.map_link}\">{self.vacancy.address}</a>\n\n"
                f"{self.vacancy.skills}\n\n"
                + (f"{_('Need passport')}!\n" if self.vacancy.has_passport else "")
                + f"{_('Payment')}: {int(self.vacancy.payment_amount)} {_('uah')} "
                  f"({self.vacancy.get_payment_unit_display()}/{self.vacancy.get_payment_method_display()})\n"
            )

    def for_creator_chat(self) -> str:
        return _('Your request has been created and is being moderated') + '\n' * 2 + self.base_format()

    def for_admin_chat(self) -> str:
        return self.base_format()

    def for_admin_refind(self) -> str:
        return _('Additional search for workers has been launched') + '\n' * 2 + self.base_format()

    def for_admin_new_feedback(self, feedback: UserFeedback) -> str:
        return _('New feedback') + '\n' * 2 + feedback.text

    def for_channel(self, status: Optional[Literal['full']] = None) -> str:
        if status == 'full':
            with override('uk'):
                return (
                    f"{self.vacancy.date.strftime('%d.%m.%Y')}\n"
                    f"{_('Sex')}: {self.vacancy.get_gender_display()}\n"
                    f"{_('Work time')}: {_('from')} {self.vacancy.start_time.strftime('%H:%M')} {_('to')} {self.vacancy.end_time.strftime('%H:%M')}\n"
                    f"{_('Number of People')}: {self.vacancy.people_count}\n\n"
                    f"{self.vacancy.skills}\n\n"
                    + (f"{_('Need passport')}!\n" if self.vacancy.has_passport else "")
                    + f"{_('Payment')}: {int(self.vacancy.payment_amount)} {_('uah')} "
                      f"({self.vacancy.get_payment_unit_display()}/{self.vacancy.get_payment_method_display()})\n"
                    + f"{_('Vacancy is close')}"
                )
        else:
            return self.base_format()

    def for_group(self) -> str:
        return self.base_format()
