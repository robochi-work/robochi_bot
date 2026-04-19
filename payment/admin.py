from django.contrib import admin

from .models import MonobankPayment


@admin.register(MonobankPayment)
class MonobankPaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice_id", "user", "vacancy", "amount_display", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("invoice_id", "order_reference")
    readonly_fields = ("invoice_id", "raw_webhook_data", "created_at", "updated_at")

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return f"{obj.amount / 100:.2f} UAH"
