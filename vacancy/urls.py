from django.urls import path
from .views import vacancy_create, vacancy_test_task, vacancy_call, vacancy_start_refind, vacancy_pre_call_check, \
    vacancy_user_feedback

app_name = 'vacancy'
urlpatterns = [
    path('create/', vacancy_create, name='create'),
    path('<int:pk>/pre-call/<str:call_type>/', vacancy_pre_call_check, name='pre_call'),
    path('<int:pk>/call/<str:call_type>/', vacancy_call, name='call'),
    path('<int:pk>/refind/', vacancy_start_refind, name='refind'),
    path('<int:pk>/feedback/', vacancy_user_feedback, name='feedback'),
    path('test-task/', vacancy_test_task, name='vacancy_test_task'),

]
