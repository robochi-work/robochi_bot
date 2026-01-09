from django.urls import path
from django.shortcuts import redirect

from .views.work_profile import (
    questionnaire_redirect,
    ProfileWizard,
    work_profile_detail,
)

app_name = "work"

urlpatterns = [
    path('wizard/', questionnaire_redirect, name='wizard'),
    path('wizard/<step>/', ProfileWizard.as_view(), name='wizard_step'),

    # ? алиас /work/agreement/ > /work/wizard/agreement/
    path('agreement/', lambda request: redirect('work:wizard_step', step='agreement'), name='agreement'),

    path('profile/', work_profile_detail, name='work_profile_detail'),
    path('agreement/', lambda request: redirect('work:agreement'), name='agreement_root'),
]

