"""Process-wide PostHog client for the FastAPI application."""

import atexit
import logging
from typing import Any, Dict, Optional

from posthog import Posthog

from backend.core.config import settings

logger = logging.getLogger(__name__)


_POSTHOG_CONFIG_VARS = ("POSTHOG_PROJECT_TOKEN", "POSTHOG_HOST")


def _posthog_configured() -> bool:
    """Return whether analytics can be safely initialized."""
    missing_vars = [
        variable
        for variable in _POSTHOG_CONFIG_VARS
        if not getattr(settings, variable, "").strip()
    ]
    if not missing_vars:
        return True

    environment = (settings.ENVIRONMENT or "").strip().lower()
    if environment not in {"production", "prod"}:
        for variable in missing_vars:
            logger.warning(
                "%s variable required by PostHog is missing or un-configured, this causes events to be silently missed. This error stops appearing once %s is configured",
                variable,
                variable,
            )
    return False


posthog_client: Optional[Posthog] = None
if _posthog_configured():
    posthog_client = Posthog(
        settings.POSTHOG_PROJECT_TOKEN,
        host=settings.POSTHOG_HOST,
        enable_exception_autocapture=True,
        privacy_mode=False,
        flush_at=1,
        flush_interval=0.5,
    )
    atexit.register(posthog_client.shutdown)


posthog_logs_logger = logging.getLogger("posthog.export")
posthog_logs_provider = None


def _configure_posthog_logs() -> None:
    """Export only records emitted by the dedicated PostHog log logger."""
    global posthog_logs_provider

    if not posthog_client:
        return

    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    except ImportError:
        logger.warning(
            "PostHog log export is unavailable until OpenTelemetry log dependencies are installed"
        )
        return

    provider = LoggerProvider()
    exporter = OTLPLogExporter(
        endpoint=f"{settings.POSTHOG_HOST.rstrip('/')}/i/v1/logs",
        headers={"Authorization": f"Bearer {settings.POSTHOG_PROJECT_TOKEN}"},
    )
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    posthog_logs_logger.addHandler(LoggingHandler(logger_provider=provider))
    posthog_logs_logger.setLevel(logging.INFO)
    posthog_logs_provider = provider


def shutdown_posthog_logs() -> None:
    """Flush PostHog log records during application shutdown."""
    if posthog_logs_provider:
        try:
            posthog_logs_provider.shutdown()
        except Exception as exc:
            logger.warning("PostHog log exporter shutdown failed: %s", type(exc).__name__)


_configure_posthog_logs()


def posthog_request_filter(scope: dict) -> bool:
    """
    Filter ASGI requests to maximize PostHog free-tier efficiency (1M events/month quota).
    Returns False to BYPASS tracking, True to KEEP instrumentation.
    """
    if scope.get("type") != "http":
        return False

    method = (scope.get("method") or "").upper()
    if method == "OPTIONS":
        return False

    path = scope.get("path") or ""

    # 1. Health checks & OpenAPI documentation (Zero analytics value)
    if path in {
        "/health",
        "/api/health",
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
        "/robots.txt",
    }:
        return False

    # 2. High-frequency polling endpoints (poll every 1-2s from web & mobile UI)
    # Skipping these prevents burning tens of thousands of requests per day on the free tier.
    if path.startswith((
        "/api/v1/uploads/batches/",
        "/api/v1/uploads/active-batch",
        "/api/v1/system/lock-status",
        "/api/v1/reports/status/",
    )):
        return False

    # 3. Static assets
    if path.startswith(("/static/", "/assets/")):
        return False

    return True


def identify_posthog_user(distinct_id: str, properties: Optional[Dict[str, Any]] = None) -> None:
    """Set person profile properties in PostHog and associate the active context."""
    if not posthog_client or not distinct_id:
        return

    uid_str = str(distinct_id).strip()
    clean_props = {k: v for k, v in (properties or {}).items() if v is not None}

    try:
        posthog_client.set(distinct_id=uid_str, properties=clean_props)
    except Exception as exc:
        logger.warning("PostHog set user properties failed for %s: %s", uid_str, type(exc).__name__)

    try:
        from posthog import identify_context
        identify_context(uid_str)
    except Exception:
        pass


def capture_posthog_event(
    event: str,
    properties: Optional[Dict[str, Any]] = None,
    distinct_id: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Capture an event without allowing analytics delivery to affect application work."""
    if not posthog_client:
        return

    props = (properties or {}).copy()
    uid = distinct_id or props.pop("distinct_id", None) or "anonymous_system_user"

    try:
        posthog_client.capture(
            event,
            distinct_id=str(uid),
            properties=props,
            **kwargs,
        )
        posthog_client.flush()
    except Exception as exc:
        logger.warning("PostHog capture failed for %s: %s", event, type(exc).__name__)


def log_user_activity(
    distinct_id: str,
    action: str,
    properties: Optional[Dict[str, Any]] = None,
) -> None:
    """
    High-level helper for capturing structured user actions efficiently.
    Sends 1 structured analytics event and 1 structured log entry to PostHog.
    """
    props = (properties or {}).copy()
    props["action"] = action
    props["environment"] = settings.ENVIRONMENT

    uid_str = str(distinct_id) if distinct_id else "anonymous_system_user"

    # 1. Product analytics event
    capture_posthog_event(
        event=f"user_{action}",
        distinct_id=uid_str,
        properties=props,
    )

    # 2. Structured log via OTLP to PostHog Logs
    if posthog_logs_provider:
        try:
            posthog_logs_logger.info(
                f"User Activity: {action} ({uid_str})",
                extra={"distinct_id": uid_str, "action": action, **props},
            )
        except Exception:
            pass


def capture_posthog_ai_generation(
    distinct_id: Optional[str], properties: dict
) -> None:
    """Capture an AI generation without allowing analytics delivery to affect the LLM call."""
    if not posthog_client:
        return

    try:
        posthog_client.capture_ai(
            "$ai_generation",
            distinct_id=distinct_id,
            properties=properties,
        )
    except Exception as exc:
        logger.warning("PostHog AI generation capture failed: %s", type(exc).__name__)
