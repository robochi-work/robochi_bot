import os
from typing import Any
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration


SENTRY_DSN = os.getenv('SENTRY_DSN', default='')
if SENTRY_DSN:
    environment = os.getenv('SENTRY_ENVIRONMENT', default='local')
    track_performance = environment == 'production'

    def traces_sampler(sampling_context: dict[str, Any]) -> float:
        if not track_performance:
            return 0

        transaction_context = sampling_context.get('transaction_context')

        if transaction_context is None:
            return 0

        op = transaction_context.get('op')

        if op is None:
            return 0

        return 1

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=environment,
        integrations=[
            DjangoIntegration(),
            # CeleryIntegration(),
        ],
        _experiments={
            'enable_logs': True
        },
        send_default_pii=True,
        traces_sampler=traces_sampler,
        profile_session_sample_rate=1.0,
        profile_lifecycle='trace'
    )