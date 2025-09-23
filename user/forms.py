from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from .models import User


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label='Password confirmation', widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ('email', 'username', 'phone_number', 'birth_year', 'language_code', 'full_name')

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 or password2:
            if password1 != password2:
                raise forms.ValidationError("Passwords don't match")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Password", help_text="You can change the password using <a href=\"../password/\">this form</a>.")

    class Meta:
        model = User
        fields = ('email', 'username', 'phone_number', 'birth_year', 'language_code', 'full_name', 'password')

    def clean_password(self):
        return self.initial["password"]