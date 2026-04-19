from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers.user import UserProfileSerializer


class UserProfileView(APIView):
    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)
