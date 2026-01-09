from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from formtools.wizard.views import SessionWizardView

from work.forms import CityForm, RoleForm
from work.models import UserWorkProfile, AgreementText

FORMS = [
    ('role', RoleForm),
    ('city', CityForm),
]

TEMPLATES = {
    'role': 'work/work_profile/role.html',
    'city': 'work/work_profile/city.html',
}


class ProfileWizard(SessionWizardView):
    form_list = FORMS

    def get_template_names(self):
        return [TEMPLATES[self.steps.current]]

    def get_form_instance(self, step):
        if step in ('city',):
            profile, _ = UserWorkProfile.objects.get_or_create(user=self.request.user)
            return profile
        return None

    def done(self, form_list, **kwargs):
        data = self.get_all_cleaned_data()
        profile, _ = UserWorkProfile.objects.get_or_create(user=self.request.user)

        profile.role = data.get('role')
        profile.city = data.get('city')
        profile.save(update_fields=['role', 'city'])

        return redirect('work:agreement')


@login_required
def questionnaire_redirect(request):
    profile, _ = UserWorkProfile.objects.get_or_create(user=request.user)

    if not profile.role:
        return redirect('work:wizard_step', step='role')

    if not profile.city:
        return redirect('work:wizard_step', step='city')

    if not profile.agreement_accepted:
        return redirect('work:agreement')

    return redirect('work:work_profile_detail')


@login_required
def work_profile_detail(request):
    profile, _ = UserWorkProfile.objects.get_or_create(user=request.user)

    return render(request, 'work/work_profile/work_profile.html', {
        'role': profile.get_role_display(),
        'city': profile.city,
    })


@login_required
def agreement_view(request):
    profile, _ = UserWorkProfile.objects.get_or_create(user=request.user)

    if not profile.role:
        return redirect('work:wizard_step', step='role')
    if not profile.city:
        return redirect('work:wizard_step', step='city')

    agreement = AgreementText.objects.filter(role=profile.role).first()

    if request.method == 'POST':
        profile.agreement_accepted = True
        profile.agreement_accepted_at = timezone.now()
        profile.is_completed = True
        profile.save(update_fields=['agreement_accepted', 'agreement_accepted_at', 'is_completed'])

        return redirect('work:work_profile_detail')

    return render(request, 'work/work_profile/agreement.html', {
        'agreement': agreement,
    })
