from rest_framework import generics

from vacancy.models import Vacancy
from api.serializers.vacancy import VacancySerializer, VacancyListSerializer


class VacancyListView(generics.ListAPIView):
    """Список активных вакансий текущего пользователя (для Заказчика)."""
    serializer_class = VacancyListSerializer

    def get_queryset(self):
        return Vacancy.objects.filter(
            owner=self.request.user
        ).exclude(status='closed').order_by('-date', '-id')


class VacancyDetailView(generics.RetrieveAPIView):
    """Детали одной вакансии."""
    serializer_class = VacancySerializer

    def get_queryset(self):
        return Vacancy.objects.filter(owner=self.request.user)
