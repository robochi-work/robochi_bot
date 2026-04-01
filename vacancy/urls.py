from django.urls import path

from .views import (
    vacancy_call,
    vacancy_close_lifecycle,
    vacancy_create,
    vacancy_detail,
    vacancy_kick_member,
    vacancy_members,
    vacancy_my_list,
    vacancy_payment,
    vacancy_pre_call_check,
    vacancy_resume_search,
    vacancy_send_contact,
    vacancy_start_refind,
    vacancy_stop_search,
    vacancy_test_task,
    vacancy_user_feedback,
    vacancy_user_list,
    vacancy_user_reviews,
)

app_name = "vacancy"
urlpatterns = [
    path("create/", vacancy_create, name="create"),
    path("my/", vacancy_my_list, name="my_list"),
    path("<int:pk>/detail/", vacancy_detail, name="detail"),
    path("<int:pk>/pre-call/<str:call_type>/", vacancy_pre_call_check, name="pre_call"),
    path("<int:pk>/call/<str:call_type>/", vacancy_call, name="call"),
    path("<int:pk>/refind/", vacancy_start_refind, name="refind"),
    path("<int:pk>/stop-search/", vacancy_stop_search, name="stop_search"),
    path("<int:pk>/resume-search/", vacancy_resume_search, name="resume_search"),
    path("<int:pk>/close-lifecycle/", vacancy_close_lifecycle, name="close_lifecycle"),
    path("<int:pk>/members/", vacancy_members, name="members"),
    path("<int:pk>/kick/<int:user_id>/", vacancy_kick_member, name="kick_member"),
    path("<int:pk>/users/", vacancy_user_list, name="user_list"),
    path("<int:pk>/feedback/<int:user_id>/", vacancy_user_feedback, name="feedback"),
    path("<int:pk>/user/<int:user_id>/reviews/", vacancy_user_reviews, name="user_reviews"),
    path("<int:pk>/send-contact/", vacancy_send_contact, name="send_contact"),
    path("<int:pk>/payment/", vacancy_payment, name="payment"),
    path("test-task/", vacancy_test_task, name="vacancy_test_task"),
]
