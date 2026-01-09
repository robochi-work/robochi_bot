from django.urls import path
from django.shortcuts import redirect

from work.views.work_profile import (
    questionnaire_redirect,
    ProfileWizard,
    work_profile_detail,
    agreement_view,
)

app_name = 'work'

urlpatterns = [
    path('agreement/', agreement_view, name='agreement'),
    path('profile/', work_profile_detail, name='work_profile_detail'),

    path('wizard/', questionnaire_redirect, name='wizard'),
    path('wizard/<step>/', ProfileWizard.as_view(), name='wizard_step'),
]