from django.utils.translation import gettext_lazy as _

GENDER_MALE = 'M'
GENDER_FEMALE = 'F'

USER_GENDER_CHOICES = [
    (GENDER_MALE, _('Male')),
    (GENDER_FEMALE, _('Female')),
]