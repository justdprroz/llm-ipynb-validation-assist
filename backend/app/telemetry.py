"""Optional OpenTelemetry bootstrap (no hard dependency on OTel packages)."""

from __future__ import annotations

import logging
import os

from app.config import get_settings

_log = logging.getLogger(__name__)


def setup_telemetry(service_name: str) -> None:
    settings = get_settings()
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    resource = None
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError:
        _log.warning("OTEL_EXPORTER_OTLP_ENDPOINT set but opentelemetry SDK not installed")
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _log.info("OTel traces configured: service=%s endpoint=%s", service_name, endpoint)

    # Auto-instrument FastAPI routes → every request gets a span
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import-not-found]
        FastAPIInstrumentor().instrument()
        _log.debug("OTel FastAPI auto-instrumentation enabled")
    except ImportError:
        _log.debug("opentelemetry-instrumentation-fastapi not installed, skipping")

    # Auto-instrument httpx → outbound calls to scraper/storage-manager get spans
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # type: ignore[import-not-found]
        HTTPXClientInstrumentor().instrument()
        _log.debug("OTel httpx auto-instrumentation enabled")
    except ImportError:
        _log.debug("opentelemetry-instrumentation-httpx not installed, skipping")

    # OTel logging bridge: Python log records → OTLP logs → collector → Loki
    # Provides trace-context correlation on log lines (trace_id, span_id fields).
    if resource is not None:
        try:
            from opentelemetry.sdk.logs import LoggerProvider, LoggingHandler  # type: ignore[import-not-found]
            from opentelemetry.sdk.logs.export import BatchLogRecordProcessor  # type: ignore[import-not-found]
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter  # type: ignore[import-not-found]
            from opentelemetry._logs import set_logger_provider  # type: ignore[import-not-found]

            log_provider = LoggerProvider(resource=resource)
            log_provider.add_log_record_processor(
                BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
            )
            set_logger_provider(log_provider)
            bridge = LoggingHandler(level=logging.DEBUG, logger_provider=log_provider)
            logging.getLogger().addHandler(bridge)
            _log.debug("OTel logging bridge installed (logs → OTLP → Loki)")
        except Exception as exc:
            _log.debug("OTel logging bridge not available: %s", exc)
