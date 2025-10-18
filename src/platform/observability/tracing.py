"""
OpenTelemetry tracing configuration for distributed observability.

Provides:
- Auto-instrumentation for FastAPI, SQLAlchemy, Redis
- Manual span creation helpers
- Context propagation across Kafka messages
- Jaeger export for local development
"""

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


class TracingConfig:
    """
    Centralized OpenTelemetry tracing configuration.

    Usage:
        # Initialize once at app startup
        tracing = TracingConfig(service_name="ticketing-service")
        tracing.setup()

        # Get tracer for manual spans
        tracer = tracing.get_tracer(__name__)
    """

    def __init__(
        self,
        *,
        service_name: str,
        otlp_endpoint: str | None = None,
        enable_console: bool = False,
    ) -> None:
        """
        Initialize tracing configuration.

        Args:
            service_name: Name of the service (e.g., "ticketing-service")
            otlp_endpoint: OTLP exporter endpoint (e.g., "http://jaeger:4317")
            enable_console: Enable console span export for debugging
        """
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint or os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')
        self.enable_console = (
            enable_console or os.getenv('OTEL_CONSOLE_EXPORT', 'false').lower() == 'true'
        )

        self._provider: TracerProvider | None = None

    def setup(self) -> None:
        """
        Setup OpenTelemetry tracing with OTLP exporter.

        Should be called once at application startup.
        Exports traces to Jaeger via OTLP protocol (port 4317).
        """
        # Create resource with service name
        resource = Resource(attributes={SERVICE_NAME: self.service_name})

        # Create tracer provider
        self._provider = TracerProvider(resource=resource)

        # Add OTLP exporter (works with Jaeger's OTLP receiver)
        if self.otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint)
            self._provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Add console exporter for debugging
        if self.enable_console:
            console_exporter = ConsoleSpanExporter()
            self._provider.add_span_processor(BatchSpanProcessor(console_exporter))

        # Set global tracer provider
        trace.set_tracer_provider(self._provider)

    def instrument_fastapi(self, *, app: Any) -> None:
        """
        Auto-instrument FastAPI application.

        Args:
            app: FastAPI application instance
        """
        FastAPIInstrumentor.instrument_app(app)

    def instrument_sqlalchemy(self, *, engine: Any) -> None:
        """
        Auto-instrument SQLAlchemy engine.

        Args:
            engine: SQLAlchemy engine instance (AsyncEngine or Engine)

        Note:
            For AsyncEngine, automatically extracts and instruments the
            underlying sync_engine since OpenTelemetry events don't support
            async engines.
        """
        # Handle AsyncEngine by instrumenting its sync_engine
        if hasattr(engine, 'sync_engine'):
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        else:
            SQLAlchemyInstrumentor().instrument(engine=engine)

    def instrument_redis(self) -> None:
        """
        Auto-instrument Redis client globally.
        """
        RedisInstrumentor().instrument()

    def get_tracer(self, *, name: str) -> trace.Tracer:
        """
        Get a tracer for manual span creation.

        Args:
            name: Tracer name (typically __name__ of the module)

        Returns:
            OpenTelemetry Tracer instance
        """
        return trace.get_tracer(name)

    def shutdown(self) -> None:
        """
        Shutdown tracing and flush remaining spans.

        Should be called on application shutdown.
        """
        if self._provider:
            self._provider.shutdown()


# Helper function for context propagation in Kafka messages
def inject_trace_context(*, headers: dict[str, str] | None = None) -> dict[str, str]:
    """
    Inject current trace context into Kafka message headers.

    Usage:
        headers = inject_trace_context()
        producer.send(topic="bookings", value=data, headers=headers)

    Args:
        headers: Existing headers dictionary (optional)

    Returns:
        Headers dictionary with injected trace context
    """
    from opentelemetry.propagate import inject

    headers = headers or {}
    inject(headers)
    return headers


def extract_trace_context(*, headers: dict[str, str] | None = None) -> None:
    """
    Extract trace context from Kafka message headers.

    Usage:
        extract_trace_context(headers=message.headers())
        with tracer.start_as_current_span("process_message"):
            # This span will be linked to the producer's trace
            process_message(message)

    Args:
        headers: Kafka message headers dictionary
    """
    from opentelemetry.propagate import extract

    if headers:
        extract(headers)
