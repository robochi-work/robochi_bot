from django.db import models
from django.utils.translation import gettext_lazy as _
from parler.models import TranslatedFields, TranslatableModel


class City(TranslatableModel):
    translations = TranslatedFields(
        name=models.CharField(_('City name'), max_length=255, null=True, blank=True),
    )

    def __str__(self):
        return f'{self.name}'

    class Meta:
        verbose_name = _("City")
        verbose_name_plural = _("Cities")
