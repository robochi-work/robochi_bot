from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from formtools.wizard.views import SessionWizardView

from telegram.service.common import get_payload_url
from work.forms import CityForm, ContactForm, CitySelectForm, RoleForm
from work.models import UserWorkProfile
from work.service.events import WORK_PROFILE_COMPLETED
from work.service.subscriber_setup import work_publisher

FORMS = [
    ('role', RoleForm),
    ('city', CityForm),
    ('contact', ContactForm),
]

TEMPLATES = {
    'role': 'work/work_profile/step_city.html',
    'city': 'work/work_profile/step_city.html',
    'contact': 'work/work_profile/step_contact.html',
}


class ProfileWizard(SessionWizardView):
    form_list = FORMS

    def get_template_names(self):
        return [TEMPLATES[self.steps.current]]

    def get_form_kwargs(self, step):
        kw = super().get_form_kwargs(step)
        if step == 'contact':
            kw['user'] = self.request.user
        return kw

    def get_form_instance(self, step):
        if step in ('city'):
            profile, _ = UserWorkProfile.objects.get_or_create(user=self.request.user)
            return profile
        return None

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        if self.steps.current == 'contact':
            payload = {"type": 'info'}
            context['info_link'] = get_payload_url(payload=payload)
        return context

    def done(self, form_list, **kwargs):
        data = self.get_all_cleaned_data()

        user = self.request.user
        user.full_name = data['full_name']
        user.birth_year = data['birth_year']
        user.gender = data['gender']
        user.save(update_fields=['full_name', 'birth_year', 'gender'])

        profile, _ = UserWorkProfile.objects.get_or_create(user=user)
        profile.city = data['city']
        profile.phone_number = data['phone_number']
        profile.role = data['role']
        profile.is_completed = True
        profile.save(update_fields=['city', 'phone_number', 'is_completed', 'role'])

        work_publisher.notify(WORK_PROFILE_COMPLETED, data={'user': user})

        return redirect('index')


@login_required
def questionnaire_redirect(request):
    profile, _ = UserWorkProfile.objects.get_or_create(user=request.user)

    if not profile.role:
        return redirect('work:anketa_step', step='role')

    if not profile.city:
        return redirect('work:anketa_step', step='city')

    user = request.user
    if not (user.full_name and user.birth_year and user.gender):
        return redirect('work:anketa_step', step='contact')

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


