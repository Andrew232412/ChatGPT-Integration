import logging
import os

import sentry_sdk
from dotenv import load_dotenv
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

load_dotenv()

sentry = sentry_sdk.init(
    dsn=os.getenv("SENTRY_KEY"),
    integrations=[
        # LoggingIntegration(
        #     level=logging.INFO,  # Capture info and above as breadcrumbs
        #     event_level=logging.WARNING,  # Send records as events
        # ),
        AwsLambdaIntegration(timeout_warning=True)
    ],
)
logging.getLogger().setLevel(logging.INFO)
