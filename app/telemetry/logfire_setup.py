"""Distributed Telemetry and Observability setup with Pydantic Logfire."""

import logging
from app.core.config import settings

logger = logging.getLogger("underwriting.telemetry")


_configured = False


def configure_logfire(app=None):
    """Initializes Logfire telemetry if token is present."""
    global _configured
    if not settings.LOGFIRE_TOKEN or settings.LOGFIRE_TOKEN.startswith("your_"):
        logger.info("Logfire token not configured; running with standard logging.")
        return

    try:
        import logfire
        if not _configured:
            logfire.configure(
                token=settings.LOGFIRE_TOKEN,
                service_name=settings.LOGFIRE_PROJECT_NAME,
                environment=settings.ENVIRONMENT
            )
            logfire.instrument_pydantic()
            _configured = True
            logger.info(f"Logfire telemetry successfully configured for project '{settings.LOGFIRE_PROJECT_NAME}'.")
        
        if app:
            logfire.instrument_fastapi(app)
    except Exception as e:
        logger.warning(f"Could not initialize Logfire: {e}")
