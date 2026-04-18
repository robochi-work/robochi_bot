from django.contrib.auth.decorators import login_required
from django.urls import path

from work.views.admin_panel import (
    admin_block_user,
    admin_close_vacancy,
    admin_dashboard,
    admin_delete_vacancy,
    admin_moderate_vacancy,
    admin_search_users,
    admin_search_vacancies,
    admin_vacancy_card,
)
from work.views.apply_vacancy import apply_vacancy_view
from work.views.employer import employer_cities, employer_faq, employer_reviews
from work.views.legal import legal_offer_view
from work.views.phone_required import phone_required_view, resend_phone_request
from work.views.work_profile import (
    ProfileWizard,
    questionnaire_redirect,
)
from work.views.worker import worker_faq, worker_reviews

app_name = "work"
urlpatterns = [
    path("wizard/", questionnaire_redirect, name="wizard"),
    path("wizard/<step>/", login_required(ProfileWizard.as_view()), name="wizard_step"),
    path("legal/offer/", legal_offer_view, name="legal_offer"),
    path("phone-required/", phone_required_view, name="phone_required"),
    path("phone-required/resend/", resend_phone_request, name="resend_phone"),
    # Worker pages
    path("reviews/", worker_reviews, name="worker_reviews"),
    path("faq/", worker_faq, name="worker_faq"),
    # Employer pages
    path("employer/reviews/", employer_reviews, name="employer_reviews"),
    path("employer/faq/", employer_faq, name="employer_faq"),
    path("employer/cities/", employer_cities, name="employer_cities"),
    # Admin panel pages
    path("admin-panel/", admin_dashboard, name="admin_dashboard"),
    path("admin-panel/users/", admin_search_users, name="admin_search_users"),
    path("admin-panel/vacancies/", admin_search_vacancies, name="admin_search_vacancies"),
    path("admin-panel/user/<int:user_id>/vacancies/", admin_vacancy_card, name="admin_vacancy_card"),
    path("admin-panel/user/<int:user_id>/block/", admin_block_user, name="admin_block_user"),
    path("admin-panel/vacancy/<int:vacancy_id>/moderate/", admin_moderate_vacancy, name="admin_moderate_vacancy"),
    path("admin-panel/vacancy/<int:vacancy_id>/close/", admin_close_vacancy, name="admin_close_vacancy"),
    path("admin-panel/vacancy/<int:vacancy_id>/delete/", admin_delete_vacancy, name="admin_delete_vacancy"),
    # Apply vacancy (WebApp entry point for channel button)
    path("apply/<int:vacancy_id>/", apply_vacancy_view, name="apply_vacancy"),
]
