from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from formtools.wizard.views import SessionWizardView
from django.utils.decorators import method_decorator

from work.choices import WorkProfileRole
from work.forms import CityForm, RoleForm, GenderForm, AgreementForm
from work.models import UserWorkProfile, AgreementText
from work.service.events import WORK_PROFILE_COMPLETED
from work.service.subscriber_setup import work_publisher
from django.utils import timezone

FORMS = [
    ('role', RoleForm),
    ('gender', GenderForm),
    ('city', CityForm),
    ('agreement', AgreementForm),
]

TEMPLATES = {
    'role': 'work/work_profile/role.html',
    'gender': 'work/work_profile/step_gender.html',
    'city': 'work/work_profile/step_city.html',
    'agreement': 'work/work_profile/step_agreement.html',
}


def show_gender_step(wizard):
    """Show gender step only for Worker role."""
    cleaned_data = wizard.get_cleaned_data_for_step('role') or {}
    return cleaned_data.get('role') == WorkProfileRole.WORKER


CONDITION_DICT = {
    'gender': show_gender_step,
}


@method_decorator(login_required, name='dispatch')
class ProfileWizard(SessionWizardView):
    form_list = FORMS
    condition_dict = CONDITION_DICT

    def get_template_names(self):
        return [TEMPLATES[self.steps.current]]

    def get_form_instance(self, step):
        if step == 'city':
            profile, _ = UserWorkProfile.objects.get_or_create(user=self.request.user)
            return profile
        return None

    def get_form_kwargs(self, step):
        return super().get_form_kwargs(step)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)

        if self.steps.current == 'agreement':
            role_data = self.get_cleaned_data_for_step('role') or {}
            role = role_data.get('role')
            agreement = AgreementText.objects.filter(role=role).first()
            context['agreement'] = agreement

        return context

    def done(self, form_list, **kwargs):
        data = self.get_all_cleaned_data()
        user = self.request.user

        profile, _ = UserWorkProfile.objects.get_or_create(user=user)

        profile.role = data.get('role')
        profile.city = data.get('city')

        profile.agreement_accepted = True
        profile.agreement_accepted_at = timezone.now()

        profile.is_completed = True

        profile.save(update_fields=[
            'role', 'city',
            'agreement_accepted', 'agreement_accepted_at',
            'is_completed'
        ])

        # Save gender only for Worker
        if profile.role == WorkProfileRole.WORKER:
            gender = data.get('gender')
            if gender:
                user.gender = gender
                user.save(update_fields=['gender'])

        work_publisher.notify(WORK_PROFILE_COMPLETED, data={'user': user})

        return redirect('/')


@login_required
def questionnaire_redirect(request):
    if not request.user.phone_number:
        return redirect('work:phone_required')

    profile, _ = UserWorkProfile.objects.get_or_create(user=request.user)

    if not profile.role:
        return redirect('work:wizard_step', step='role')

    if not profile.city:
        return redirect('work:wizard_step', step='city')

    if not profile.agreement_accepted:
        return redirect('work:wizard_step', step='agreement')

    return redirect('/')
