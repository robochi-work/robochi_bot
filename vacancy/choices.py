from django.utils.translation import gettext_lazy as _

from user.choices import GENDER_FEMALE, GENDER_MALE

DATE_TODAY = "now"
DATE_TOMORROW = "tomorrow"
DATE_CHOICES = [
    (DATE_TODAY, _("Today")),
    (DATE_TOMORROW, _("Tomorrow")),
]


GENDER_ANY = "X"
GENDER_CHOICES = [
    (GENDER_MALE, _("Male")),
    (GENDER_FEMALE, _("Female")),
    (GENDER_ANY, _("Any")),
]

PAYMENT_HOUR = "hour"
PAYMENT_SHIFT = "shift"
PAYMENT_UNIT_CHOICES = [
    (PAYMENT_HOUR, _("Per hour")),
    (PAYMENT_SHIFT, _("Per shift")),
]
PAYMENT_CASH = "cash"
PAYMENT_CARD = "card"
PAYMENT_METHOD_CHOICES = [
    (PAYMENT_CASH, _("Cash")),
    (PAYMENT_CARD, _("Card")),
]

STATUS_CREATED = "created"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_ACTIVE = "active"
STATUS_REJECTED = "rejected"
STATUS_CLOSED = "closed"
STATUS_SEARCH_STOPPED = "stopped"
STATUS_AWAITING_PAYMENT = "awaiting"
STATUS_CHOICES = [
    (STATUS_PENDING, _("Очікує модерації")),
    (STATUS_APPROVED, _("Активна")),
    (STATUS_REJECTED, _("Скасована модератором")),
    (STATUS_ACTIVE, _("Активна")),
    (STATUS_CLOSED, _("Закрита")),
    (STATUS_SEARCH_STOPPED, _("Пошук зупинено")),
    (STATUS_AWAITING_PAYMENT, _("Очікує оплати")),
]
