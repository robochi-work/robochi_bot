from telegram.models import Channel
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED, STATUS_PENDING
from vacancy.models import Vacancy
from work.blocks.base import PageBlock
from work.blocks.registry import block_registry


@block_registry.register
class ActiveVacanciesPreviewBlock(PageBlock):
    order = 2
    statuses = [STATUS_PENDING, STATUS_APPROVED, STATUS_ACTIVE]

    def is_visible(self, request):
        return Vacancy.objects.filter(
            owner=request.user, status__in=self.statuses,
        ).exists()

    def get_context(self, request):
        return {
            'vacancies': Vacancy.objects.filter(
                owner=request.user, status__in=self.statuses,
            ).all()
        }

    @property
    def template_name(self):
        return f'work/blocks/active_vacancies_preview.html'

