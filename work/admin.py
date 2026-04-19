from django.contrib import admin

from work.models import AgreementText, FaqItem


@admin.register(AgreementText)
class AgreementTextAdmin(admin.ModelAdmin):
    list_display = ("role", "title", "updated_at")
    list_editable = ("title",)


@admin.register(FaqItem)
class FaqItemAdmin(admin.ModelAdmin):
    list_display = ("role", "question_short", "order", "is_active", "has_image", "has_video", "updated_at")
    list_filter = ("role", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("question", "answer")
    ordering = ("role", "order")

    @admin.display(description="Питання")
    def question_short(self, obj):
        return obj.question[:80]

    @admin.display(boolean=True, description="Фото")
    def has_image(self, obj):
        return bool(obj.image)

    @admin.display(boolean=True, description="Відео")
    def has_video(self, obj):
        return bool(obj.video_url)
