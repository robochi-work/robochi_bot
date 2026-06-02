from django.utils.translation import override

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
        from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

        users_call = VacancyUserCall.objects.filter(
            vacancy_user__in=self.vacancy.members,
            status=CallStatus.REJECT,
            call_type=call_type,
        )
        with override("uk"):
            call_label = "1 перекличка" if call_type == CallType.START else "2 перекличка"
            owner_block = format_user_block_with_contact(self.vacancy.owner, self.vacancy)
            group = format_group_link(self.vacancy)
            from vacancy.models import VacancyContactPhone

            contact_phones = dict(
                VacancyContactPhone.objects.filter(
                    vacancy=self.vacancy,
                    user_id__in=[uc.vacancy_user.user_id for uc in users_call],
                ).values_list("user_id", "phone")
            )
            user_lines = "\n".join(
                [
                    f"{contact_phones.get(uc.vacancy_user.user_id, '—')} — "
                    f"{uc.vacancy_user.user.full_name or uc.vacancy_user.user.id}"
                    for uc in users_call
                ]
            )
            return (
                f"⚠️ Спірна ситуація — {call_label}\n\n"
                f"Вакансія: {self.vacancy.address}\n\n"
                f"Замовник:\n{owner_block}\n\n"
                f"Зняті працівники:\n{user_lines}"
                f"{group}"
            )

    def admin_start_call_fail_detailed(self) -> str:
        """Admin notification with employer data for failed first rollcall."""
        from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

        with override("uk"):
            owner_block = format_user_block_with_contact(self.vacancy.owner, self.vacancy)
            group = format_group_link(self.vacancy)
            return (
                f"⚠️ 1 перекличка— недостатньо робітників\n\n"
                f"Вакансія: {self.vacancy.address}\n\n"
                f"Замовник:\n{owner_block}"
                f"{group}"
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
        from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

        with override("uk"):
            owner_block = format_user_block_with_contact(self.vacancy.owner, self.vacancy)
            group = format_group_link(self.vacancy)
            return f"🔒 Вакансію закрито\n\nАдреса: {self.vacancy.address}\n\nЗамовник:\n{owner_block}{group}"

    def vacancy_payment_no_exist_admin(self) -> str:
        from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

        with override("uk"):
            owner_block = format_user_block_with_contact(self.vacancy.owner, self.vacancy)
            group = format_group_link(self.vacancy)
            return f"💰 Вакансія не оплачена\n\nАдреса: {self.vacancy.address}\n\nЗамовник:\n{owner_block}{group}"

    # ─── Admin: employer unchecked ALL workers at rollcall ─────────────────

    def admin_all_unchecked(self, call_type: CallType) -> str:
        from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

        with override("uk"):
            call_label = "1 перекличка" if call_type == CallType.START else "2 перекличка"
            owner_block = format_user_block_with_contact(self.vacancy.owner, self.vacancy)
            group = format_group_link(self.vacancy)
            return (
                f"🚫 Замовник зняв усі відмітки — {call_label}\n\n"
                f"Вакансія: {self.vacancy.address}\n\n"
                f"Замовник:\n{owner_block}"
                f"{group}"
            )

    # ─── Admin: employer manually closed vacancy ────────────────────────────

    def admin_employer_closed_invoice(self, members_count: int) -> str:
        from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

        with override("uk"):
            owner_block = format_user_block_with_contact(self.vacancy.owner, self.vacancy)
            group = format_group_link(self.vacancy)
            return (
                f"📋 Замовник закрив вакансію (виставлено рахунок)\n\n"
                f"Адреса: {self.vacancy.address}\n"
                f"Працівників: {members_count}\n\n"
                f"Замовник:\n{owner_block}"
                f"{group}"
            )

    def admin_employer_closed_no_workers(self) -> str:
        from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

        with override("uk"):
            owner_block = format_user_block_with_contact(self.vacancy.owner, self.vacancy)
            group = format_group_link(self.vacancy)
            return (
                f"📋 Замовник закрив вакансію\n\n"
                f"Адреса: {self.vacancy.address}\n\n"
                f"Замовник:\n{owner_block}"
                f"{group}\n"
                f"⏳ Групу буде розпущено через 3 години."
            )

    # ─── Admin: scenario B — not enough workers after confirmed rollcall ───

    def admin_scenario_b(self, confirmed: int, needed: int) -> str:
        from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

        with override("uk"):
            owner_block = format_user_block_with_contact(self.vacancy.owner, self.vacancy)
            group = format_group_link(self.vacancy)
            return (
                f"👷 Початок роботи — недостатньо робітників!\n\n"
                f"Вакансія: {self.vacancy.address}\n"
                f"Потрібно: {needed} | Підтверджено: {confirmed}\n\n"
                f"Замовник:\n{owner_block}"
                f"{group}"
            )

        # ─── Renewal (scenario 6) ─────────────────────────────────────────────────

    def renewal_offer(self) -> str:
        with override("uk"):
            vacancy_text = VacancyTelegramTextFormatter(self.vacancy).for_channel()
            return f"Бажаєте продовжити вакансію на завтра?\n\n{vacancy_text}"

    def renewal_worker_ask(self) -> str:
        with override("uk"):
            vacancy_text = VacancyTelegramTextFormatter(self.vacancy).for_channel()
            return f"Завтра будете працювати там же де сьогодні?\n\n{vacancy_text}"

    def renewal_too_many_workers(self, excess: int) -> str:
        with override("uk"):
            return (
                f"На завтра підтвердили участь більше людей, ніж потрібно. "
                f"Видаліть {excess} зайвих працівників або збільшіть кількість місць у вакансії."
            )
