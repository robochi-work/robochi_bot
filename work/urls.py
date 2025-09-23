from django.urls import path

from work.views.work_profile import questionnaire_redirect, ProfileWizard, work_profile_detail

app_name = 'work'
urlpatterns = [
    path('anketa/', questionnaire_redirect, name='anketa'),
    path('anketa/<step>/', ProfileWizard.as_view(), name='anketa_step'),
    path('profile/', work_profile_detail, name='work_profile_detail'),
]
