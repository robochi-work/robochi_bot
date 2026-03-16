from django.db import models
from django.conf import settings


class MonobankPayment(models.Model):
    class Status(models.TextChoices):
        CREATED = 'created', 'Created'
        PROCESSING = 'processing', 'Processing'
        HOLD = 'hold', 'Hold'
        SUCCESS = 'success', 'Success'
        FAILURE = 'failure', 'Failure'
        REVERSED = 'reversed', 'Reversed'
        EXPIRED = 'expired', 'Expired'

    invoice_id = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='monobank_payments'
    )
    vacancy = models.ForeignKey(
        'vacancy.Vacancy',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='monobank_payments'
    )
    order_reference = models.CharField(max_length=255, db_index=True, blank=True)
    amount = models.PositiveBigIntegerField(help_text='Amount in kopecks (smallest unit)')
    final_amount = models.PositiveBigIntegerField(null=True, blank=True)
    ccy = models.IntegerField(default=980, help_text='Currency code (980=UAH)')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    page_url = models.URLField(max_length=512, blank=True)
    mono_modified_date = models.DateTimeField(null=True, blank=True)
    masked_pan = models.CharField(max_length=20, blank=True)
    raw_webhook_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Monobank Payment'
        verbose_name_plural = 'Monobank Payments'

    def __str__(self):
        return f"Invoice {self.invoice_id} — {self.status} — {self.amount/100:.2f} UAH"
