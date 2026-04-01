from django import forms
from django.utils.translation import gettext_lazy as _

from city.models import City
from user.choices import USER_GENDER_CHOICES

from .models import UserWorkProfile, WorkProfileRole


class RoleForm(forms.ModelForm):
    ROLE_CHOICES = [
        (WorkProfileRole.EMPLOYER, _("Employer — looking for workers")),
        (WorkProfileRole.WORKER, _("Worker — looking for job")),
    ]

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        label=_("Role"),
        initial=WorkProfileRole.WORKER,
    )

    class Meta:
        model = UserWorkProfile
        fields = ["role"]


class GenderForm(forms.Form):
    gender = forms.ChoiceField(
        choices=USER_GENDER_CHOICES,
        widget=forms.RadioSelect,
        label=_("Gender"),
    )


class CityForm(forms.ModelForm):
    city = forms.ModelChoiceField(
        queryset=City.objects.all(),
        widget=forms.RadioSelect,
        label=_("City"),
    )

    class Meta:
        model = UserWorkProfile
        fields = ["city"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["city"].label_from_instance = lambda obj: obj.safe_translation_getter("name", any_language=True)


class AgreementForm(forms.Form):
    pass
