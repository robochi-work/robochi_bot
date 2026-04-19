import base64
import hashlib
import logging
from datetime import datetime

import ecdsa
import httpx
from django.conf import settings
from django.db import transaction

from .models import MonobankPayment

logger = logging.getLogger(__name__)

# Cache for Monobank public key
_mono_pubkey_cache = None


def get_monobank_pubkey() -> str:
    """Fetch and cache Monobank merchant public key."""
    global _mono_pubkey_cache
    if _mono_pubkey_cache:
        return _mono_pubkey_cache
    response = httpx.get(
        "https://api.monobank.ua/api/merchant/pubkey",
        headers={"X-Token": settings.MONOBANK_API_TOKEN},
        timeout=30.0,
    )
    response.raise_for_status()
    _mono_pubkey_cache = response.json()["key"]
    return _mono_pubkey_cache


def verify_monobank_signature(x_sign_base64: str, body: bytes) -> bool:
    """Verify Monobank webhook ECDSA signature."""
    try:
        pub_key_b64 = get_monobank_pubkey()
        pub_key = ecdsa.VerifyingKey.from_pem(base64.b64decode(pub_key_b64).decode())
        pub_key.verify(
            base64.b64decode(x_sign_base64),
            body,
            sigdecode=ecdsa.util.sigdecode_der,
            hashfunc=hashlib.sha256,
        )
        return True
    except (ecdsa.BadSignatureError, Exception) as e:
        global _mono_pubkey_cache
        _mono_pubkey_cache = None  # Reset cache on failure (key rotation)
        logger.warning(f"Monobank signature verification failed: {e}")
        return False


def create_invoice(*, user, vacancy, amount_kopecks: int, description: str = "") -> MonobankPayment:
    """Create Monobank invoice and save to DB."""
    order_ref = f"vacancy-{vacancy.id}-{user.id}"
    response = httpx.post(
        "https://api.monobank.ua/api/merchant/invoice/create",
        json={
            "amount": amount_kopecks,
            "ccy": 980,
            "redirectUrl": "https://robochi.pp.ua/payment/success/",
            "webHookUrl": "https://robochi.pp.ua/api/v1/payments/webhook/monobank/",
            "merchantPaymInfo": {
                "reference": order_ref,
                "destination": description or f"Оплата за заявку #{vacancy.id}",
            },
            "validity": 3600,
        },
        headers={"X-Token": settings.MONOBANK_API_TOKEN},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()

    payment = MonobankPayment.objects.create(
        invoice_id=data["invoiceId"],
        user=user,
        vacancy=vacancy,
        order_reference=order_ref,
        amount=amount_kopecks,
        page_url=data.get("pageUrl", ""),
        status=MonobankPayment.Status.CREATED,
    )
    return payment


@transaction.atomic
def process_webhook(*, invoice_id: str, webhook_data: dict) -> MonobankPayment | None:
    """Process Monobank webhook callback. Uses modifiedDate for idempotency."""
    try:
        payment = MonobankPayment.objects.select_for_update().get(invoice_id=invoice_id)
    except MonobankPayment.DoesNotExist:
        logger.error(f"MonobankPayment not found for invoice_id={invoice_id}")
        return None

    # Parse modifiedDate for idempotency
    modified_str = webhook_data.get("modifiedDate", "")
    if modified_str:
        modified_dt = datetime.fromisoformat(modified_str.replace("Z", "+00:00"))
        if payment.mono_modified_date and modified_dt <= payment.mono_modified_date:
            logger.info(f"Skipping stale webhook for {invoice_id}")
            return payment
        payment.mono_modified_date = modified_dt

    new_status = webhook_data.get("status", "")
    if new_status in [s.value for s in MonobankPayment.Status]:
        payment.status = new_status

    payment.final_amount = webhook_data.get("finalAmount", payment.amount)
    payment.masked_pan = webhook_data.get("paymentInfo", {}).get("maskedPan", "")
    payment.raw_webhook_data = webhook_data
    payment.save()

    # Post-payment success actions
    if payment.status == MonobankPayment.Status.SUCCESS:
        # Mark vacancy as paid
        vacancy = payment.vacancy
        if vacancy:
            vacancy.extra["is_paid"] = True
            vacancy.status = "paid"
            vacancy.save(update_fields=["extra", "status"])

        # Remove unpaid block
        from user.models import UserBlock
        from user.services import BlockService

        unpaid_block = UserBlock.objects.filter(
            user=payment.user,
            is_active=True,
            reason="unpaid",
        ).first()
        if unpaid_block:
            BlockService.unblock_user(unpaid_block.pk)

        # Delete payment message from bot
        if vacancy and vacancy.extra.get("payment_message_id"):
            try:
                from telegram.handlers.bot_instance import get_bot

                get_bot().delete_message(
                    chat_id=payment.user.id,
                    message_id=vacancy.extra["payment_message_id"],
                )
                del vacancy.extra["payment_message_id"]
                vacancy.save(update_fields=["extra"])
            except Exception:
                import sentry_sdk

                sentry_sdk.capture_exception()

        # Notify employer
        try:
            from telegram.handlers.bot_instance import get_bot

            get_bot().send_message(
                payment.user.id,
                f"Оплату за вакансію {vacancy.address} прийнято. Дякуємо!",
            )
        except Exception:
            import sentry_sdk

            sentry_sdk.capture_exception()

    return payment
