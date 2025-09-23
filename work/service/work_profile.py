from work.choices import WorkProfileRole
from work.models import UserWorkProfile
from user.models import User


class WorkProfileService:
    def __init__(self, user: User):
        self.user = user

    def create_profile(self) -> tuple[UserWorkProfile, bool]:
        return UserWorkProfile.objects.get_or_create(user=self.user)

    def get_profile(self) -> UserWorkProfile:
        try:
            return UserWorkProfile.objects.select_related('city').get(user=self.user)
        except UserWorkProfile.DoesNotExist:
            profile, created = self.create_profile()
            return profile

    def set_role(self, role: WorkProfileRole) -> UserWorkProfile:
        profile = self.get_profile()
        profile.role = role
        profile.save(update_fields=['role'])
        return profile
