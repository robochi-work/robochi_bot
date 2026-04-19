import os

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

SENTRY_DSN = os.getenv("SENTRY_DSN", default="")
if SENTRY_DSN:
    environment = os.getenv("SENTRY_ENVIRONMENT", default="local")

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=environment,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
        ],
        _experiments={"enable_logs": True},
        send_default_pii=False,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )
