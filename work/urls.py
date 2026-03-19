from django.urls import path
from django.contrib.auth.decorators import login_required
from work.views.work_profile import (
    questionnaire_redirect,
    ProfileWizard,
    work_profile_detail,
)
from work.views.legal import legal_offer_view

app_name = 'work'

urlpatterns = [
    path('profile/', work_profile_detail, name='work_profile_detail'),
    path('wizard/', questionnaire_redirect, name='wizard'),
    path('wizard/<step>/', login_required(ProfileWizard.as_view()), name='wizard_step'),
    path('legal/offer/', legal_offer_view, name='legal_offer'),
]
