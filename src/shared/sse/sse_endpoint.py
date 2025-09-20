"""
SSE Endpoint

FastAPI endpoint for Server-Sent Events with JWT authentication.
Replaces the WebSocket endpoint functionality.
"""

from fastapi import Request
from fastapi.responses import StreamingResponse

from src.shared.logging.loguru_io import Logger
from src.shared.sse.sse_config import SSEErrorMessages
from src.shared.sse.sse_message_codec import SSEMessageCodec
from src.shared.sse.ticket_sse_service import ticket_sse_service
from src.shared.service.jwt_auth_service import CustomJWTStrategy, get_jwt_strategy
from src.user.domain.user_model import User, UserRole


@Logger.io(truncate_content=True)
async def sse_ticket_updates(request: Request, event_id: int) -> StreamingResponse:
    """
    SSE endpoint with JWT authentication
    Usage: GET /api/event/sse/1
    Authentication: JWT token in 'fastapiusersauth' cookie
    """

    # Get JWT token from cookie
    token = request.cookies.get('fastapiusersauth')

    if not token:
        error_stream = _create_auth_error_stream(SSEErrorMessages.MISSING_TOKEN)
        return StreamingResponse(
            error_stream,
            media_type='text/event-stream',
            status_code=401,
            headers={'Cache-Control': 'no-cache'},
        )

    try:
        jwt_strategy = get_jwt_strategy()

        # Decode full token payload (contains all user information)
        if isinstance(jwt_strategy, CustomJWTStrategy):
            payload = jwt_strategy.decode_full_token(token)
        else:
            payload = None

        if not payload:
            error_stream = _create_auth_error_stream(SSEErrorMessages.INVALID_TOKEN)
            return StreamingResponse(
                error_stream,
                media_type='text/event-stream',
                status_code=401,
                headers={'Cache-Control': 'no-cache'},
            )

        # Check user role directly from payload
        try:
            user_role = UserRole(payload.get('role')) if payload.get('role') else None
            if user_role not in [UserRole.BUYER, UserRole.SELLER]:
                error_stream = _create_auth_error_stream(SSEErrorMessages.FORBIDDEN)
                return StreamingResponse(
                    error_stream,
                    media_type='text/event-stream',
                    status_code=403,
                    headers={'Cache-Control': 'no-cache'},
                )
        except ValueError:
            error_stream = _create_auth_error_stream(SSEErrorMessages.FORBIDDEN)
            return StreamingResponse(
                error_stream,
                media_type='text/event-stream',
                status_code=403,
                headers={'Cache-Control': 'no-cache'},
            )

        # Create User object from payload data (no database lookup needed)
        current_user = User(
            id=payload['user_id'],
            email=payload['email'],
            name=payload.get('name', 'SSE User'),
            role=user_role,
            hashed_password='',  # Not needed for SSE
            is_active=payload.get('is_active', True),
            is_superuser=False,
            is_verified=payload.get('is_verified', True),
        )

    except (ValueError, KeyError, TypeError) as e:
        Logger.base.error(f'JWT decoding error: {e}')
        error_stream = _create_auth_error_stream(SSEErrorMessages.AUTHENTICATION_FAILED)
        return StreamingResponse(
            error_stream,
            media_type='text/event-stream',
            status_code=401,
            headers={'Cache-Control': 'no-cache'},
        )

    # Authentication successful, create SSE stream
    return await ticket_sse_service.create_sse_stream(request, event_id, current_user)


async def _create_auth_error_stream(error_message: str):
    """Create an authentication error SSE stream"""
    codec = SSEMessageCodec()
    error_event = codec.create_error_event(error_message)
    yield error_event


# Function to push ticket events to SSE connections (replaces WebSocket version)
async def push_ticket_event_to_sse(
    event_id: int, ticket_data: dict, event_type: str, affected_sections: list | None = None
) -> None:
    """Push ticket events to SSE connections"""
    await ticket_sse_service.broadcast_ticket_event(
        event_id=event_id,
        ticket_data=ticket_data,
        event_type=event_type,
        affected_sections=affected_sections,
    )
