import datetime as d
import logging
from datetime import date, datetime, timedelta
from typing import Literal

from django import forms
from django.contrib.admin.widgets import AdminDateWidget
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from city.models import City
from telegram.choices import CallType
from telegram.models import Channel
from user.models import User
from work.models import UserWorkProfile

from .choices import (
    DATE_TODAY,
    DATE_TOMORROW,
    GENDER_CHOICES,
    GENDER_MALE,
    PAYMENT_CASH,
    PAYMENT_METHOD_CHOICES,
    PAYMENT_SHIFT,
    PAYMENT_UNIT_CHOICES,
)
from .models import Vacancy, VacancyUser

logger = logging.getLogger(__name__)


class TimeSelectWidget(forms.MultiWidget):
    template_name = "vacancy/widgets/time_select.html"

    def __init__(self, attrs=None):
        hour_choices = [(str(h).zfill(2), str(h).zfill(2)) for h in range(24)]
        minute_choices = [("00", "00"), ("15", "15"), ("30", "30"), ("45", "45")]
        widgets = [
            forms.Select(choices=hour_choices, attrs={"class": "time-select-hour"}),
            forms.Select(choices=minute_choices, attrs={"class": "time-select-minute"}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if isinstance(value, d.time):
            minute = value.minute
            minute = min([0, 15, 30, 45], key=lambda x: abs(x - minute))
            return [str(value.hour).zfill(2), str(minute).zfill(2)]
        if isinstance(value, str) and ":" in value:
            parts = value.split(":")
            return [parts[0].zfill(2), parts[1].zfill(2)]
        return ["00", "00"]


class TimeSelectField(forms.MultiValueField):
    def __init__(self, *args, **kwargs):
        hour_choices = [(f"{h:02d}", f"{h:02d}") for h in range(24)]
        minute_choices = [("00", "00"), ("15", "15"), ("30", "30"), ("45", "45")]
        fields = [
            forms.ChoiceField(choices=hour_choices),
            forms.ChoiceField(choices=minute_choices),
        ]
        kwargs["widget"] = TimeSelectWidget()
        kwargs.setdefault("require_all_fields", True)
        super().__init__(*args, fields=fields, **kwargs)

    def compress(self, data_list):
        if data_list and len(data_list) == 2:
            return d.time(int(data_list[0]), int(data_list[1]))
        return None


class VacancyAdminForm(forms.ModelForm):
    date = forms.DateField(required=False)
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}), label=_("Start Time"))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}), label=_("End Time"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gender"].initial = "A"
        self.fields["people_count"].initial = 1
        self.fields["has_passport"].initial = False
        self.fields["address"].initial = "тестовый адрес"
        self.fields["date"].initial = datetime.now().date() + timedelta(days=1)
        self.fields["start_time"].initial = d.time(7, 0)
        self.fields["end_time"].initial = d.time(16, 0)
        self.fields["payment_amount"].initial = 800
        self.fields["date_choice"].initial = "today"
        self.fields["payment_unit"].initial = "shift"
        self.fields["payment_method"].initial = "cash"
        self.fields["skills"].initial = "Ответственность, пунктуальность"

    def clean_people_count(self) -> int:
        value = self.cleaned_data["people_count"]
        if not (1 <= value <= 20):
            raise ValidationError(_("Number of people must be between 1 and 20."), code="invalid")
        return value

    def clean_start_time(self) -> int:
        value = self.cleaned_data["start_time"]

        return value

    class Meta:
        model = Vacancy
        fields = [
            "owner",
            "gender",
            "people_count",
            "has_passport",
            "address",
            "map_link",
            "date",
            "start_time",
            "end_time",
            "payment_amount",
            "date_choice",
            "payment_unit",
            "payment_method",
            "skills",
            "contact_phone",
            "status",
            "group",
            "channel",
            "extra",
            "search_active",
            "closed_at",
            "search_stopped_at",
            "first_rollcall_passed",
            "second_rollcall_passed",
        ]
        widgets = {
            "date": AdminDateWidget(),
        }


class VacancyForm(forms.Form):
    date_choice = forms.ChoiceField(
        label=_("Preferred Date"),
        widget=forms.RadioSelect(attrs={"class": "date-choice"}),
    )

    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        label=_("Preferred Gender"),
        initial=GENDER_MALE,
    )

    people_count = forms.IntegerField(
        label=_("Number of People"),
        min_value=1,
        max_value=20,
    )
    has_passport = forms.BooleanField(required=False, label=_("Has Passport"))
    address = forms.CharField(min_length=4, max_length=255, label=_("Address"))
    map_link = forms.URLField(required=False, label=_("Map Link (is not required)"))
    start_time = TimeSelectField(label=_("Start Time"))
    end_time = TimeSelectField(label=_("End Time"))
    payment_amount = forms.DecimalField(max_digits=8, decimal_places=2, label=_("Payment Amount"))
    payment_unit = forms.ChoiceField(choices=PAYMENT_UNIT_CHOICES, label=_("Payment Type"), initial=PAYMENT_SHIFT)
    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        label=_("Payment method"),
        initial=PAYMENT_CASH,
    )
    skills = forms.CharField(widget=forms.Textarea(attrs={"rows": 7}), label=_("What will they do"))
    contact_phone = forms.CharField(
        max_length=20,
        required=False,
        label=_("Contact phone"),
        widget=forms.TextInput(attrs={"type": "tel", "placeholder": "+380..."}),
    )

    city = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label=_("City"),
        widget=forms.Select(attrs={"class": "city-select"}),
    )

    def __init__(self, *args, **kwargs):
        self.work_profile = kwargs.pop("work_profile", None)
        resume_mode = kwargs.pop("resume_mode", False)
        super().__init__(*args, **kwargs)

        if resume_mode:
            self.fields["address"].widget.attrs["readonly"] = True
            self.fields["address"].widget.attrs["class"] = "readonly-field"
            if "map_link" in self.fields:
                self.fields["map_link"].widget.attrs["readonly"] = True
                self.fields["map_link"].widget.attrs["class"] = "readonly-field"

        # Configure city field based on multi_city_enabled
        if self.work_profile and self.work_profile.multi_city_enabled:
            # All allowed cities + main city
            allowed_ids = list(self.work_profile.allowed_cities.values_list("id", flat=True))
            if self.work_profile.city_id:
                allowed_ids.append(self.work_profile.city_id)
            self.fields["city"].queryset = City.objects.filter(id__in=allowed_ids)
            if self.work_profile.city_id:
                self.fields["city"].initial = self.work_profile.city_id
            self.fields["city"].required = True
        else:
            # Single city — hide field, set to profile city
            self.fields["city"].widget = forms.HiddenInput()
            if self.work_profile and self.work_profile.city:
                self.fields["city"].queryset = City.objects.filter(id=self.work_profile.city_id)
                self.fields["city"].initial = self.work_profile.city_id
            else:
                self.fields["city"].queryset = City.objects.none()

        today = date.today()
        tomorrow_str = (today + timedelta(days=1)).strftime("%d.%m.%Y")
        self.fields["date_choice"].choices = [
            (DATE_TODAY, mark_safe(f"<div>{_('Today')}</div> <div>{today.strftime('%d.%m.%Y')}</div>")),
            (DATE_TOMORROW, mark_safe(f"<div>{_('Tomorrow')}</div> <div>{tomorrow_str}</div>")),
        ]
        self.fields["date_choice"].initial = DATE_TODAY

    def clean_contact_phone(self):
        import re

        phone = self.cleaned_data.get("contact_phone", "").strip()
        if not phone:
            return phone
        cleaned = re.sub(r"[\s\-\(\)]", "", phone)
        phone_re = re.compile(r"^(\+380\d{9}|380\d{9}|0\d{9})$")
        if not phone_re.match(cleaned):
            raise forms.ValidationError("Введіть коректний номер телефону!")
        return cleaned

    def clean_map_link(self):
        link = self.cleaned_data.get("map_link")
        if link:
            link = link.strip()
            if not link.startswith("https://maps.app"):
                raise forms.ValidationError(_("The map link must start with https://maps.app"))
        return link

    def clean_date_choice(self):
        date_choice = self.cleaned_data.get("date_choice")

        try:
            if date_choice == DATE_TODAY:
                self.cleaned_data["date"] = date.today()
            elif date_choice == DATE_TOMORROW:
                self.cleaned_data["date"] = date.today() + timedelta(days=1)
            else:
                raise ValueError()
        except (ValueError, TypeError) as err:
            raise ValidationError(_("Invalid date format")) from err

        return date_choice

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        date_choice = cleaned_data.get("date_choice")

        if start_time and end_time:
            from datetime import datetime, timedelta

            from django.utils import timezone

            # Check: if today, start_time must be >= now + 2 hours
            if date_choice == DATE_TODAY:
                now = timezone.localtime(timezone.now())
                min_start = (now + timedelta(hours=1)).time()
                if start_time < min_start:
                    raise ValidationError(
                        _("Start time must be at least 1 hour from now (earliest: %(time)s)."),
                        code="too_early",
                        params={"time": min_start.strftime("%H:%M")},
                    )

            # Check: minimum shift duration 3 hours
            dummy_date = datetime(2000, 1, 1)
            start_dt = datetime.combine(dummy_date, start_time)
            end_dt = datetime.combine(dummy_date, end_time)

            # Handle overnight shifts (end_time < start_time means next day)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            diff = end_dt - start_dt
            min_hours = 3
            if diff < timedelta(hours=min_hours):
                raise ValidationError(
                    _("Minimum shift duration is %(hours)s hours."),
                    code="min_duration",
                    params={"hours": min_hours},
                )

            max_hours = 12
            if diff > timedelta(hours=max_hours):
                raise ValidationError(
                    _("Maximum shift duration is %(hours)s hours."),
                    code="max_duration",
                    params={"hours": max_hours},
                )

        return cleaned_data

    def save(self, owner: User, status) -> Vacancy:
        data = self.cleaned_data
        work_profile = UserWorkProfile.objects.get(user=owner)

        # Determine city: from form field (multi-city) or from profile
        selected_city = data.get("city")
        if not selected_city:
            selected_city = work_profile.city

        vacancy = Vacancy.objects.create(
            owner=owner,
            status=status,
            date_choice=data.get("date_choice"),
            gender=data.get("gender"),
            people_count=data.get("people_count"),
            has_passport=data.get("has_passport"),
            address=data.get("address"),
            map_link=data.get("map_link"),
            date=data.get("date"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            payment_amount=data.get("payment_amount"),
            payment_unit=data.get("payment_unit"),
            payment_method=data.get("payment_method"),
            skills=data.get("skills"),
            contact_phone=data.get("contact_phone", ""),
            channel=Channel.objects.get(city=selected_city),
        )
        logger.info(
            "vacancy_created",
            extra={"owner_id": owner.id, "city": str(selected_city), "people_count": data.get("people_count")},
        )
        return vacancy


CallTypes = Literal["start", "after_start"]


class VacancyCallForm(forms.Form):
    CALL_TYPE_CHOICES = (CallType.START[0], CallType.AFTER_START[0])
    users = forms.ModelMultipleChoiceField(
        queryset=VacancyUser.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Выберите пользователей",
    )
    call_type = forms.CharField(widget=forms.HiddenInput(), required=True)

    def __init__(self, *args, call_type: CallTypes | CallType, queryset: QuerySet[VacancyUser] | None = None, **kwargs):
        kwargs.setdefault("initial", {})["call_type"] = call_type
        if "data" in kwargs and isinstance(kwargs["data"], dict):
            data = kwargs["data"].copy()
            if "call_type" not in data:
                data["call_type"] = call_type
                kwargs["data"] = data

        super().__init__(*args, **kwargs)

        if queryset is not None:
            self.fields["users"].queryset = queryset
            self.fields["users"].label_from_instance = self.user_label_from_instance

    @staticmethod
    def user_label_from_instance(obj: VacancyUser):
        return f"{obj.user.full_name or f'Ім’я не визначене <{obj.user.id}>'} "


class VacancyUserFeedbackForm(forms.Form):
    rating = forms.ChoiceField(
        choices=[("like", "Лайк"), ("dislike", "Дизлайк")],
        required=False,
        widget=forms.RadioSelect,
    )
    text = forms.CharField(widget=forms.Textarea, required=False)

    def clean(self):
        cleaned_data = super().clean()
        rating = cleaned_data.get("rating")
        text = (cleaned_data.get("text") or "").strip()
        if not rating and not text:
            raise forms.ValidationError("Вкажіть оцінку або залиште відгук.")
        cleaned_data["text"] = text
        return cleaned_data
