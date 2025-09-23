from telegram.models import Channel
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED, STATUS_PENDING
from vacancy.forms import VacancyForm
from vacancy.models import Vacancy
from work.blocks import ActiveVacanciesPreviewBlock
from work.blocks.base import PageBlock
from work.blocks.registry import block_registry


@block_registry.register
class VacancyCreateFormBlock(PageBlock):
    order = 2
    statuses = ActiveVacanciesPreviewBlock.statuses

    def is_visible(self, request):
        return not Vacancy.objects.filter(
            owner=request.user, status__in=self.statuses,
        ).exists()

    def get_context(self, request):
        return {
            'form': VacancyForm()
        }

    @property
    def template_name(self):
        return f'work/blocks/vacancy_create_form.html'

