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

from opentelemetry import context as otel_context, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON


class TracingConfig:
    """
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

        # Sampling strategy: ALWAYS_ON at SDK level
        # - Head-based sampling can't capture errors (error status unknown at span start)
        # - For production volume control, use tail-based sampling in collector
        #   (e.g., Jaeger, Tempo) to: keep 100% errors, sample 10% of success traces
        sampler = ALWAYS_ON

        # Create tracer provider with sampler
        self._provider = TracerProvider(resource=resource, sampler=sampler)

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

    def instrument_fastapi(self, *, app: Any, excluded_urls: str = 'health,metrics,ping') -> None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded_urls)

    def instrument_sqlalchemy(self, *, engine: Any) -> None:
        if hasattr(engine, 'sync_engine'):  # Handle AsyncEngine by instrumenting its sync_engine
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        else:
            SQLAlchemyInstrumentor().instrument(engine=engine)

    def instrument_redis(self) -> None:
        RedisInstrumentor().instrument()

    def get_tracer(self, *, name: str) -> trace.Tracer:
        """
        Args:
            name: Tracer name (typically __name__ of the module)

        Returns:
            OpenTelemetry Tracer instance
        """
        return trace.get_tracer(name)

    def shutdown(self) -> None:
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


def extract_trace_context(*, headers: dict[str, str] | None = None) -> Context:
    """
    Extract trace context from Kafka message headers and attach to current context.

    This enables distributed tracing across services by propagating trace context
    through Kafka messages. The consumer can continue the same trace started by
    the producer.

    Flow::

        Producer (Ticketing)              Consumer (Reservation)
              │                                  │
              ├─  Span: publish_event            │
              │   headers: {traceparent:...}     │
              │   ───────────────────────────>   │
              │                                  ├─ Span: process_message (child)
              │                                  │    └─ Span: reserve_seats
              │                                  │
              └──────────── Same Trace ──────────┘

    Example:
        Producer side (inject trace context)::

            headers = inject_trace_context() # headers = {"traceparent": "00-{trace_id}-{span_id}-01"}
            producer.send("topic", value=event, headers=headers)

        Consumer side (extract and continue trace)::

            def handle_message(message):
                # Extract trace context from Kafka headers
                ctx = extract_trace_context(headers=dict(message.headers()))

                # New spans will be children of the producer's span
                with tracer.start_as_current_span("process_message", context=ctx):
                    process_booking_event(message.value())

    Args:
        headers: Kafka message headers dictionary containing trace context
            (e.g., {"traceparent": "00-abc123-def456-01"})

    Returns:
        Context object with extracted trace context, or current context if no headers
    """
    if headers:
        # Extract returns a new Context with the propagated data
        ctx = extract(headers)
        # Attach the context to make it the current context
        otel_context.attach(ctx)
        return ctx
    return otel_context.get_current()
