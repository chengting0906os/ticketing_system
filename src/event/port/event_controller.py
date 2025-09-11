"""Event controller."""

from typing import List, Optional

from fastapi import APIRouter, Depends, status

from src.event.port.event_schema import (
    EventCreateRequest,
    EventResponse,
    EventUpdateRequest,
)
from src.event.use_case.event_use_case import (
    CreateEventUseCase,
    DeleteEventUseCase,
    GetEventUseCase,
    ListEventsUseCase,
    UpdateEventUseCase,
)
from src.shared.exception.exceptions import NotFoundError
from src.shared.logging.loguru_io import Logger
from src.shared.service.role_auth_service import require_seller
from src.user.domain.user_model import User


router = APIRouter()


@router.post('', status_code=status.HTTP_201_CREATED)
@Logger.io
async def create_event(
    request: EventCreateRequest,
    current_user: User = Depends(require_seller),
    use_case: CreateEventUseCase = Depends(CreateEventUseCase.depends),
) -> EventResponse:
    event = await use_case.create(
        name=request.name,
        description=request.description,
        price=request.price,
        seller_id=current_user.id,  # Use current user's ID
        is_active=request.is_active,
    )

    if event.id is None:
        raise ValueError('Event ID should not be None after creation.')

    return EventResponse(
        id=event.id,
        name=event.name,
        description=event.description,
        price=event.price,
        seller_id=event.seller_id,
        is_active=event.is_active,
        status=event.status.value,  # Convert enum to string
    )


@router.patch('/{event_id}', status_code=status.HTTP_200_OK)
async def update_event(
    event_id: int,
    request: EventUpdateRequest,
    current_user: User = Depends(require_seller),
    use_case: UpdateEventUseCase = Depends(UpdateEventUseCase.depends),
) -> EventResponse:
    event = await use_case.update(
        event_id=event_id,
        name=request.name,
        description=request.description,
        price=request.price,
        is_active=request.is_active,
    )

    if not event:
        raise NotFoundError(f'Event with id {event_id} not found')

    return EventResponse(
        id=event_id,
        name=event.name,
        description=event.description,
        price=event.price,
        seller_id=event.seller_id,
        is_active=event.is_active,
        status=event.status.value,
    )


@router.delete('/{event_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int,
    current_user: User = Depends(require_seller),
    use_case: DeleteEventUseCase = Depends(DeleteEventUseCase.depends),
):
    await use_case.delete(event_id)
    return None


@router.get('/{event_id}', status_code=status.HTTP_200_OK)
async def get_event(
    event_id: int, use_case: GetEventUseCase = Depends(GetEventUseCase.depends)
) -> EventResponse:
    event = await use_case.get_by_id(event_id)

    if not event:
        raise NotFoundError(f'Event with id {event_id} not found')

    return EventResponse(
        id=event_id,
        name=event.name,
        description=event.description,
        price=event.price,
        seller_id=event.seller_id,
        is_active=event.is_active,
        status=event.status.value,
    )


@router.get('', status_code=status.HTTP_200_OK)
async def list_events(
    seller_id: Optional[int] = None,
    use_case: ListEventsUseCase = Depends(ListEventsUseCase.depends),
) -> List[EventResponse]:
    if seller_id is not None:
        events = await use_case.get_by_seller(seller_id)
    else:
        events = await use_case.list_available()

    result = []
    for event in events:
        if event.id is not None:
            result.append(
                EventResponse(
                    id=event.id,
                    name=event.name,
                    description=event.description,
                    price=event.price,
                    seller_id=event.seller_id,
                    is_active=event.is_active,
                    status=event.status.value,
                )
            )
    return result
