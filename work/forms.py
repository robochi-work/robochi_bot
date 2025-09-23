import datetime

from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from city.models import City
from user.choices import USER_GENDER_CHOICES
from .models import UserWorkProfile, WorkProfileRole

User = get_user_model()


class RoleForm(forms.ModelForm):
    ROLE_CHOICES = [
        (
            WorkProfileRole.EMPLOYER,
            _('Employer — looking for workers')
        ),
        (
            WorkProfileRole.WORKER,
            _('Worker — looking for job')
        ),
    ]

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
        label=_('Role'),
        initial=WorkProfileRole.WORKER,
    )

    class Meta:
        model = UserWorkProfile
        fields = ['role']


class CityForm(forms.ModelForm):
    city = forms.ModelChoiceField(
        queryset=City.objects.all(),
        widget=forms.RadioSelect,
        label=_('City'),
    )

    class Meta:
        model = UserWorkProfile
        fields = ['city']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['city'].label_from_instance = (
            lambda obj: obj.safe_translation_getter('name', any_language=True)
        )

class CitySelectForm(CityForm):
    city = forms.ModelChoiceField(
        queryset=City.objects.all(),
        widget=forms.Select,
        label=_('City'),
    )




class ContactForm(forms.Form):
    gender = forms.ChoiceField(
        choices=USER_GENDER_CHOICES,
        label=_('Gender'),
    )
    full_name = forms.CharField(
        max_length=150,
        label=_('How can I contact you?'),
        required=False,
        widget=forms.TextInput(attrs={'placeholder': ''}),
    )
    phone_number = forms.CharField(
        max_length=20,
        label=_('Contact phone number (+380 xx xxx xxxx)'),
        widget=forms.TextInput(
            attrs={
                'placeholder': '+380 00 000 0000',
                'pattern': r'\+380\s?\d{2}\s?\d{3}\s?\d{4}',
                'type': 'tel',
                'value': '+380'
            }
        ),
    )
    birth_year = forms.IntegerField(
        label=_('Year of birth'),
        min_value=1900,
        max_value=datetime.date.today().year,
        widget=forms.NumberInput(attrs={
            'placeholder': _('Enter your year of birth')
        })
    )


    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields['full_name'].initial = user.full_name
            self.fields['birth_year'].initial = user.birth_year
            profile, _ = UserWorkProfile.objects.get_or_create(user=user)
            self.fields['phone_number'].initial = profile.phone_number

    def clean_phone_number(self):
        pn = self.cleaned_data['phone_number'].strip()
        if not pn.startswith('+380'):
            raise forms.ValidationError(_('The number must start with +380'))
        return pn

    def save(self):
        user = self.user
        user.full_name = self.cleaned_data['full_name']
        user.birth_year = self.cleaned_data['birth_year']
        user.save(update_fields=['full_name', 'birth_year', ])

        profile, _ = UserWorkProfile.objects.get_or_create(user=user)
        profile.phone_number = self.cleaned_data['phone_number']
        profile.save(update_fields=['phone_number'])
        return profile
