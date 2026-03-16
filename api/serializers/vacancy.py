from rest_framework import serializers

from vacancy.models import Vacancy, VacancyUser


class VacancySerializer(serializers.ModelSerializer):
    workers_count = serializers.SerializerMethodField()

    class Meta:
        model = Vacancy
        fields = [
            'id', 'date_choice', 'date', 'start_time', 'end_time',
            'gender', 'people_count', 'skills', 'has_passport',
            'address', 'map_link', 'payment_amount', 'payment_unit',
            'payment_method', 'status', 'workers_count', 'extra',
        ]
        read_only_fields = ['id', 'status', 'extra']

    def get_workers_count(self, obj):
        return VacancyUser.objects.filter(
            vacancy=obj,
            status='member'
        ).count()


class VacancyListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vacancy
        fields = ['id', 'date_choice', 'date', 'address', 'status', 'people_count', 'payment_amount']
