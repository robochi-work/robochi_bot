from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from formtools.wizard.views import SessionWizardView

from telegram.service.common import get_payload_url
from work.forms import CityForm, ContactForm, CitySelectForm, RoleForm, AgreementForm
from work.models import UserWorkProfile, AgreementText
from work.service.events import WORK_PROFILE_COMPLETED
from work.service.subscriber_setup import work_publisher
from django.utils import timezone

FORMS = [
    ('role', RoleForm),
    ('city', CityForm),
    ('agreement', AgreementForm),
]

TEMPLATES = {
    'role': 'work/work_profile/step_city.html',
    'city': 'work/work_profile/step_city.html',
    'agreement': 'work/work_profile/step_agreement.html',
}

class ProfileWizard(SessionWizardView):
    form_list = FORMS

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
            profile, _ = UserWorkProfile.objects.get_or_create(user=self.request.user)
            agreement = AgreementText.objects.filter(role=profile.role).first()
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

        work_publisher.notify(WORK_PROFILE_COMPLETED, data={'user': user})

        return redirect('work:work_profile_detail')


@login_required
def questionnaire_redirect(request):
    profile, _ = UserWorkProfile.objects.get_or_create(user=request.user)

    if not profile.role:
        return redirect('work:wizard_step', step='role')

    if not profile.city:
        return redirect('work:wizard_step', step='city')

    if not profile.agreement_accepted:
        return redirect('work:wizard_step', step='agreement')

    return redirect('work:work_profile_detail')


@login_required
def work_profile_detail(request):
    user = request.user
    profile, _ = UserWorkProfile.objects.get_or_create(user=user)

    city_form = CitySelectForm(request.POST, instance=profile, prefix='city')
    city_form.fields['city'].disabled = True

    if request.method == 'POST':
        contact_form = ContactForm(request.POST, user=user, prefix='contact')
        if city_form.is_valid() and contact_form.is_valid():
            city_form.save()
            contact_form.save()
            return redirect('work:work_profile_detail')
    else:
        contact_form = ContactForm(user=user, prefix='contact')

    return render(request, 'work/work_profile/work_profile.html', {
        'role': profile.get_role_display(),
        'city_form': city_form,
        'contact_form': contact_form,
    })


