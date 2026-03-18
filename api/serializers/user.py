from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    city_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'full_name', 'username', 'phone_number', 'gender', 'role', 'city_name']
        read_only_fields = ['id', 'phone_number']

    def get_role(self, obj):
        profile = getattr(obj, 'work_profile', None)
        return profile.role if profile else None

    def get_city_name(self, obj):
        profile = getattr(obj, 'work_profile', None)
        if profile and profile.city:
            return str(profile.city)
        return None
