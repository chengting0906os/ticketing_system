from collections.abc import Callable
from datetime import datetime
from enum import Enum
from functools import singledispatch
from typing import Any

import attrs
import uuid_utils

from src.platform.message_queue.proto import domain_event_pb2 as pb


# ============================================================================
# Configuration
# ============================================================================

_EVENT_TYPE_TO_PROTO: dict[str, type] = {
    'BookingCreatedDomainEvent': pb.BookingCreatedDomainEvent,
    'BookingPaidEvent': pb.BookingPaidEvent,
    'BookingCancelledEvent': pb.BookingCancelledEvent,
}


# ============================================================================
# Value Converters (singledispatch)
# ============================================================================


@singledispatch
def _to_proto_value(value: Any) -> Any:
    return value


@_to_proto_value.register(uuid_utils.UUID)
def _(value: uuid_utils.UUID) -> str:
    return str(value)


@_to_proto_value.register(datetime)
def _(value: datetime) -> int:
    return int(value.timestamp() * 1000)


@_to_proto_value.register(Enum)
def _(value: Enum) -> Any:
    return value.value


# ============================================================================
# Field Converters
# ============================================================================


def _to_proto_subsection_config(value: Any) -> pb.SubsectionConfig:
    return pb.SubsectionConfig(rows=value.rows, cols=value.cols, price=value.price)


_TO_PROTO_FIELD_CONVERTERS: dict[str, Callable[[Any], Any]] = {
    'config': _to_proto_subsection_config,
}


# ============================================================================
# Public API (Production)
# ============================================================================


def get_proto_class_by_event_type(event_type: str) -> type:
    proto_class = _EVENT_TYPE_TO_PROTO.get(event_type)
    if not proto_class:
        raise ValueError(f'Unknown event type: {event_type}')
    return proto_class


def convert_domain_event_to_proto(
    event: object, trace_context: dict[str, str] | None = None
) -> Any:
    """Convert domain event to protobuf message with optional trace context."""
    proto_class = get_proto_class_by_event_type(event.__class__.__name__)
    event_dict = _attrs_to_proto_dict(event)
    # Inject trace context if provided
    if trace_context:
        event_dict['traceparent'] = trace_context.get('traceparent', '')
        event_dict['tracestate'] = trace_context.get('tracestate', '')
    return proto_class(**event_dict)


# ============================================================================
# Internal Implementation
# ============================================================================


def _attrs_to_proto_dict(event: object) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for field in attrs.fields(event.__class__):
        name = field.name
        value = getattr(event, name)

        if name in _TO_PROTO_FIELD_CONVERTERS:
            # Nested message fields: skip if None (protobuf doesn't accept None for messages)
            if value is not None:
                result[name] = _TO_PROTO_FIELD_CONVERTERS[name](value)
        else:
            result[name] = _to_proto_value(value)

    return result
