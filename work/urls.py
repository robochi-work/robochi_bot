from django.urls import path
from django.contrib.auth.decorators import login_required
from work.views.work_profile import (
    questionnaire_redirect,
    ProfileWizard,
)
from work.views.legal import legal_offer_view
from work.views.phone_required import phone_required_view, resend_phone_request
from work.views.worker import worker_reviews, worker_faq

app_name = 'work'
urlpatterns = [
    path('wizard/', questionnaire_redirect, name='wizard'),
    path('wizard/<step>/', login_required(ProfileWizard.as_view()), name='wizard_step'),
    path('legal/offer/', legal_offer_view, name='legal_offer'),
    path('phone-required/', phone_required_view, name='phone_required'),
    path('phone-required/resend/', resend_phone_request, name='resend_phone'),
    # Worker pages
    path('reviews/', worker_reviews, name='worker_reviews'),
    path('faq/', worker_faq, name='worker_faq'),
]
