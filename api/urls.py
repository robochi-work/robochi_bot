from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView

from api.views.auth import TelegramAuthView
from api.views.payment import MonobankWebhookView
from api.views.user import UserProfileView
from api.views.vacancy import VacancyDetailView, VacancyListView

app_name = "api"

v1_urlpatterns = [
    # Auth
    path("auth/telegram/", TelegramAuthView.as_view(), name="auth_telegram"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # User
    path("users/me/", UserProfileView.as_view(), name="user_profile"),
    # Vacancies
    path("vacancies/", VacancyListView.as_view(), name="vacancy_list"),
    path("vacancies/<int:pk>/", VacancyDetailView.as_view(), name="vacancy_detail"),
    # Payments
    path("payments/webhook/monobank/", MonobankWebhookView.as_view(), name="monobank_webhook"),
]

urlpatterns = [
    path("v1/", include((v1_urlpatterns, "v1"))),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
]
