import json
import logging

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from payment.services import verify_monobank_signature, process_webhook

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class MonobankWebhookView(APIView):
    """
    Monobank sends POST with JSON body and X-Sign header.
    Must return 200 to stop retries.
    No authentication — verified via ECDSA signature.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        body = request.body
        x_sign = request.headers.get('X-Sign', '')

        if not x_sign or not verify_monobank_signature(x_sign, body):
            logger.warning('Monobank webhook: invalid signature')
            return HttpResponse(status=200)  # Return 200 anyway to stop retries

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return HttpResponse(status=200)

        invoice_id = data.get('invoiceId', '')
        if invoice_id:
            payment = process_webhook(invoice_id=invoice_id, webhook_data=data)
            if payment and payment.status == 'success' and payment.vacancy_id:
                try:
                    vacancy = payment.vacancy
                    if not vacancy.extra.get('is_paid'):
                        vacancy.extra['is_paid'] = True
                        vacancy.save(update_fields=['extra'])
                        logger.info(f'Vacancy {vacancy.pk} marked as paid via webhook')
                except Exception as e:
                    logger.warning(f'Failed to update vacancy after payment: {e}')

        return HttpResponse(status=200)
