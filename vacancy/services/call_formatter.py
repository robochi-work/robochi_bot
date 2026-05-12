from django.conf import settings
from django.utils.translation import override

from service.common import get_admin_url
from telegram.choices import CallStatus, CallType
from vacancy.models import Vacancy, VacancyUserCall
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter


class CallVacancyTelegramTextFormatter:
    def __init__(self, vacancy: Vacancy):
        self.vacancy = vacancy

    # ─── Worker: 2h before shift ─────────────────────────────────────────────

    def before_start_call(self) -> str:
        with override("uk"):
            vacancy_text = VacancyTelegramTextFormatter(self.vacancy).for_channel()
            return f"Через 2 години початок роботи за вакансією:\n{vacancy_text}\n\nВи точно будете?"

    # ─── Employer: rollcall prompts ───────────────────────────────────────────

    def start_call(self) -> str:
        with override("uk"):
            return (
                f"Початок роботи за вакансією-\n"
                f"Адреса: {self.vacancy.address}\n"
                f"Проведіть перекличку серед працівників- натисніть кнопку нижче."
            )

    def final_call(self) -> str:
        with override("uk"):
            return (
                f"Скоро завершення роботи за вакансією-\n"
                f"Адреса: {self.vacancy.address}\n"
                f"Підтвердіть хто відпрацював до кінця зміни- натисніть кнопку нижче."
            )

    # ─── Employer: invoice after second rollcall ──────────────────────────────

    def invoice_final_call_success(self) -> str:
        with override("uk"):
            return "Оплата послуг підбору працівників"

    # ─── Worker: marked absent at rollcall ───────────────────────────────────

    def start_call_fail(self) -> str:
        with override("uk"):
            invite = f"\n{self.vacancy.group.invite_link}" if self.vacancy.group else ""
            return f"Замовник зазначив вашу відсутність на перекличці.{invite}"

    # ─── Admin: disputed rollcall ─────────────────────────────────────────────

    def admin_call_fail(self, call_type: CallType) -> str:
        users_call = VacancyUserCall.objects.filter(
            vacancy_user__in=self.vacancy.members,
            status=CallStatus.REJECT,
            call_type=call_type,
        )
        with override("uk"):
            owner = self.vacancy.owner
            owner_phone = self._get_owner_contact_phone() or "\u2014"
            employer_block = f"<b>ID:</b> <code>{owner.pk}</code>" + "\n"
            employer_block += f"<b>\u0406\u043c\u2019\u044f:</b> {owner.full_name or chr(8212)}" + "\n"
            if owner.username:
                employer_block += f"<b>Username:</b> @{owner.username}" + "\n"
            else:
                employer_block += "<b>Username:</b> \u2014" + "\n"
            employer_block += f"<b>\u0422\u0435\u043b\u0435\u0444\u043e\u043d:</b> {owner_phone}" + "\n"
            from vacancy.models import VacancyContactPhone

            contact_phones = dict(
                VacancyContactPhone.objects.filter(
                    vacancy=self.vacancy,
                    user_id__in=[uc.vacancy_user.user_id for uc in users_call],
                ).values_list("user_id", "phone")
            )
            user_lines = "\n".join(
                [
                    f"{contact_phones.get(uc.vacancy_user.user_id, '—')} - "
                    f"<a href='{settings.BASE_URL.rstrip('/') + get_admin_url(uc.vacancy_user.user)}'>"
                    f"{uc.vacancy_user.user.full_name or uc.vacancy_user.user.id}</a>"
                    for uc in users_call
                ]
            )
            invite = f"\n{self.vacancy.group.invite_link}" if self.vacancy.group else ""
            return (
                f"Спірна ситуація по заявці {self.vacancy.address}. "
                f"Замовник зняв відмітки з деяких працівників.\n"
                f"{employer_block}\n"
                f"{user_lines}{invite}"
            )

    def admin_start_call_fail_detailed(self) -> str:
        """Admin notification with employer data for failed first rollcall."""
        owner = self.vacancy.owner
        phone = self._get_owner_contact_phone() or chr(8212)
        with override("uk"):
            user_block = f"<b>ID:</b> <code>{owner.pk}</code>" + chr(10)
            user_block += f"<b>{chr(1030)}{chr(1084)}{chr(8217)}{chr(1103)}:</b> {owner.full_name or chr(8212)}" + chr(
                10
            )
            if owner.username:
                user_block += f"<b>Username:</b> @{owner.username}" + chr(10)
            else:
                user_block += "<b>Username:</b> " + chr(8212) + chr(10)
            user_block += (
                f"<b>{chr(1058)}{chr(1077)}{chr(1083)}{chr(1077)}{chr(1092)}{chr(1086)}{chr(1085)}:</b> {phone}"
                + chr(10)
            )
            invite = ""
            if self.vacancy.group and self.vacancy.group.invite_link:
                invite = chr(10) + self.vacancy.group.invite_link
            return (
                f"{chr(9888)}{chr(65039)} 1 {chr(1087)}{chr(1077)}{chr(1088)}{chr(1077)}{chr(1082)}{chr(1083)}{chr(1080)}{chr(1095)}{chr(1082)}{chr(1072)}{chr(8212)} "
                f"{chr(1085)}{chr(1077)}{chr(1076)}{chr(1086)}{chr(1089)}{chr(1090)}{chr(1072)}{chr(1090)}{chr(1085)}{chr(1100)}{chr(1086)} "
                f"{chr(1088)}{chr(1086)}{chr(1073)}{chr(1110)}{chr(1090)}{chr(1085)}{chr(1080)}{chr(1082)}{chr(1110)}{chr(1074)}"
                + chr(10)
                + chr(10)
                + f"{chr(1042)}{chr(1072)}{chr(1082)}{chr(1072)}{chr(1085)}{chr(1089)}{chr(1110)}{chr(1103)}: {self.vacancy.address}"
                + chr(10)
                + f"{user_block}"
                + f"{invite}"
            )

    def admin_start_call_fail(self) -> str:
        return self.admin_call_fail(call_type=CallType.START)

    def admin_after_start_call_fail(self) -> str:
        return self.admin_call_fail(call_type=CallType.AFTER_START)

    def admin_after_start_call_fail_detailed(self) -> str:
        with override("uk"):
            owner = self.vacancy.owner
            phone = self._get_owner_contact_phone() or "—"
            username_line = f"<b>Username:</b> @{owner.username}\n" if owner.username else "<b>Username:</b> —\n"
            user_block = (
                f"<b>ID:</b> <code>{owner.pk}</code>\n"
                f"<b>Ім'я:</b> {owner.full_name or '—'}\n" + username_line + f"<b>Телефон:</b> {phone}\n"
            )
            invite = (
                f"\n{self.vacancy.group.invite_link}" if self.vacancy.group and self.vacancy.group.invite_link else ""
            )
            return f"⚠️ 2 перекличка— недостатньо робітників\n\nВакансія: {self.vacancy.address}\n{user_block}{invite}"

    # ─── Worker: join confirmation ────────────────────────────────────────────

    def worker_join_confirm(self) -> str:
        with override("uk"):
            vacancy_text = VacancyTelegramTextFormatter(self.vacancy).for_channel()
            return f"Ви обрали вакансію:\n{vacancy_text}\n\nПідтвердіть, що ви дійсно готові працювати."

    def worker_join_reminder(self) -> str:
        with override("uk"):
            return f"Нагадуємо: підтвердіть, будь ласка, свою участь у вакансії за адресою {self.vacancy.address}."

    # ─── Static: auto-block notifications ────────────────────────────────────

    @staticmethod
    def auto_block_message(reason: str = "неявка на перекличку") -> str:
        with override("uk"):
            return (
                f"Вас заблоковано у сервісі robochi.work !\n"
                f"Причина: {reason}.\n"
                f"Для розблокування зверніться до Адміністратора- @robochi_work_admin"
            )

    # ─── Static: vacancy lifecycle notifications ──────────────────────────────

    @staticmethod
    def vacancy_created_user() -> str:
        with override("uk"):
            return (
                "Ваша вакансія для пошуку працівників відправлена на модерацію.\n"
                "Ви можете керувати вакансієй у Власному Кабінеті.\n"
                "Перегляньте як керувати вакансієй."
            )

    @staticmethod
    def vacancy_approved_user() -> str:
        with override("uk"):
            return "Вашу вакансію схвалено та опубліковано для пошуку робітників.\nПерейдіть до керування вакансієй- ви зможете спілкуватися з робітниками у групі, контролювати та редагувати вакансію."

    def _get_owner_contact_phone(self) -> str | None:
        from vacancy.models import VacancyContactPhone

        cp = VacancyContactPhone.objects.filter(vacancy=self.vacancy, user=self.vacancy.owner).first()
        return cp.phone if cp else None

    def vacancy_closed_admin(self) -> str:
        owner = self.vacancy.owner
        with override("uk"):
            return (
                f"🔒 Вакансію закрито\n"
                f"Адреса: {self.vacancy.address}\n"
                f"Замовник: {owner.full_name or str(owner.id)}\n"
                f"Телефон: {self._get_owner_contact_phone() or '—'}"
            )

    def vacancy_payment_no_exist_admin(self) -> str:
        with override("uk"):
            group_link = self.vacancy.group.invite_link if self.vacancy.group else "—"
            return f"Вакансія не оплачена по закінченню часу.\n{group_link}"

    # ─── Renewal (scenario 6) ─────────────────────────────────────────────────

    def renewal_offer(self) -> str:
        with override("uk"):
            vacancy_text = VacancyTelegramTextFormatter(self.vacancy).for_channel()
            return f"Бажаєте продовжити вакансію на завтра?\n\n{vacancy_text}"

    def renewal_worker_ask(self) -> str:
        with override("uk"):
            vacancy_text = VacancyTelegramTextFormatter(self.vacancy).for_channel()
            return f"Завтра будете працювати там же де сьогодні?\n\n{vacancy_text}"

    def renewal_worker_reminder(self) -> str:
        with override("uk"):
            return f"Нагадуємо: підтвердіть участь на завтра за адресою {self.vacancy.address}."

    def renewal_too_many_workers(self, excess: int) -> str:
        with override("uk"):
            return (
                f"На завтра підтвердили участь більше людей, ніж потрібно. "
                f"Видаліть {excess} зайвих працівників або збільшіть кількість місць у вакансії."
            )
