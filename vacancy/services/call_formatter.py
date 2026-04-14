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
            return f"Початок роботи за заявкою {self.vacancy.address}.\nПроведіть перекличку серед працівників."

    def final_call(self) -> str:
        with override("uk"):
            return (
                f"Скоро завершення роботи за заявкою {self.vacancy.address}.\n"
                f"Підтвердіть, хто відпрацював до кінця зміни."
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
            user_lines = "\n".join(
                [
                    f"{uc.vacancy_user.user.phone_number} - "
                    f"<a href='{settings.BASE_URL.rstrip('/') + get_admin_url(uc.vacancy_user.user)}'>"
                    f"{uc.vacancy_user.user.full_name or uc.vacancy_user.user.id}</a>"
                    for uc in users_call
                ]
            )
            invite = f"\n{self.vacancy.group.invite_link}" if self.vacancy.group else ""
            return (
                f"Спірна ситуація по заявці {self.vacancy.address}. "
                f"Замовник зняв відмітки з деяких працівників.\n"
                f"{user_lines}{invite}"
            )

    def admin_start_call_fail(self) -> str:
        return self.admin_call_fail(call_type=CallType.START)

    def admin_after_start_call_fail(self) -> str:
        return self.admin_call_fail(call_type=CallType.AFTER_START)

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
                "Ваша заявка на пошук працівників відправлена на модерацію.\n"
                "Статус можна переглянути в розділі «Поточні заявки»."
            )

    @staticmethod
    def vacancy_approved_user() -> str:
        with override("uk"):
            return "Вашу заявку схвалено та опубліковано в каналі.\nПерейти до керування заявкою:"

    def vacancy_closed_admin(self) -> str:
        owner = self.vacancy.owner
        with override("uk"):
            return (
                f"🔒 Вакансію закрито\n"
                f"Адреса: {self.vacancy.address}\n"
                f"Замовник: {owner.full_name or str(owner.id)}\n"
                f"Телефон: {getattr(owner, 'phone_number', None) or '—'}"
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
