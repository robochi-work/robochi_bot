from django.db import models
from django.utils.translation import gettext_lazy as _

GENDER_MALE = "M"
GENDER_FEMALE = "F"

USER_GENDER_CHOICES = [
    (GENDER_MALE, _("Male")),
    (GENDER_FEMALE, _("Female")),
]


class BlockType(models.TextChoices):
    TEMPORARY = "temporary", _("Тимчасове блокування")
    PERMANENT = "permanent", _("Постійне блокування")


class BlockReason(models.TextChoices):
    MANUAL = "manual", _("Ручне (адміністратор)")
    ROLLCALL_REJECT = "rollcall_reject", _("Неявка на перекличку")
    EMPLOYER_UNCHECK = "employer_uncheck", _("Зняття галочки замовником")
    UNPAID = "unpaid", _("Неоплачений рахунок")
    EMPLOYER_NO_GROUP = "employer_no_group", _("Замовник не зайшов у групу вакансії")
    OTHER = "other", _("Інше")
