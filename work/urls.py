from django.urls import path
from django.contrib.auth.decorators import login_required
from work.views.work_profile import (
    questionnaire_redirect,
    ProfileWizard,
)
from work.views.legal import legal_offer_view
from work.views.phone_required import phone_required_view, resend_phone_request
from work.views.worker import worker_reviews, worker_faq
from work.views.admin_panel import (
    admin_dashboard,
    admin_search_users,
    admin_search_vacancies,
    admin_vacancy_card,
    admin_block_user,
)

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
    # Admin panel pages
    path('admin-panel/', admin_dashboard, name='admin_dashboard'),
    path('admin-panel/users/', admin_search_users, name='admin_search_users'),
    path('admin-panel/vacancies/', admin_search_vacancies, name='admin_search_vacancies'),
    path('admin-panel/user/<int:user_id>/vacancies/', admin_vacancy_card, name='admin_vacancy_card'),
    path('admin-panel/user/<int:user_id>/block/', admin_block_user, name='admin_block_user'),
]
