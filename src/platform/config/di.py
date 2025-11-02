"""
https://python-dependency-injector.ets-labs.org/index.html
https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html
"""

from dependency_injector import containers, providers

from src.platform.config.core_setting import Settings
from src.platform.database.db_setting import Database
from src.platform.message_queue.kafka_config_service import KafkaConfigService
from src.service.seat_reservation.app.command.finalize_seat_payment_use_case import (
    FinalizeSeatPaymentUseCase,
)
from src.service.seat_reservation.app.command.release_seat_use_case import ReleaseSeatUseCase
from src.service.seat_reservation.app.command.reserve_seats_use_case import ReserveSeatsUseCase
from src.service.seat_reservation.domain.seat_selection_domain import SeatSelectionDomain
from src.service.seat_reservation.driven_adapter.seat_reservation_mq_publisher import (
    SeatReservationEventPublisher,
)
from src.service.seat_reservation.driven_adapter.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)
from src.service.seat_reservation.driven_adapter.seat_state_query_handler_impl import (
    SeatStateQueryHandlerImpl,
)
from src.service.ticketing.driven_adapter.message_queue.booking_event_publisher_impl import (
    BookingEventPublisherImpl,
)
from src.service.ticketing.driven_adapter.message_queue.mq_infra_orchestrator_impl import (
    MqInfraOrchestrator,
)
from src.service.ticketing.driven_adapter.repo.booking_command_repo_impl import (
    BookingCommandRepoImpl,
)
from src.service.ticketing.driven_adapter.repo.booking_query_repo_impl import BookingQueryRepoImpl
from src.service.ticketing.driven_adapter.repo.event_ticketing_command_repo_impl import (
    EventTicketingCommandRepoImpl,
)
from src.service.ticketing.driven_adapter.repo.event_ticketing_query_repo_impl import (
    EventTicketingQueryRepoImpl,
)
from src.service.ticketing.driven_adapter.repo.user_command_repo_impl import UserCommandRepoImpl
from src.service.ticketing.driven_adapter.repo.user_query_repo_impl import UserQueryRepoImpl
from src.service.ticketing.driven_adapter.state.booking_metadata_handler_impl import (
    BookingMetadataHandlerImpl,
)
from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)
from src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl import (
    SeatAvailabilityQueryHandlerImpl,
)
from src.service.ticketing.driving_adapter.http_controller.auth.jwt_auth import JwtAuth
from src.platform.event.in_memory_broadcaster import InMemoryEventBroadcasterImpl


class Container(containers.DeclarativeContainer):
    # Configuration
    config_service = providers.Singleton(Settings)

    # Database (uses AsyncEngineManager with settings from config_service)
    database = providers.Singleton(Database, read_only=False)

    # Infrastructure services
    kafka_service = providers.Singleton(KafkaConfigService)

    # Background task group (set by main.py lifespan)
    # Used for fire-and-forget tasks like event publishing
    task_group = providers.Object(None)

    # Repositories - session will be injected by use cases
    # Command repos use raw SQL with asyncpg (no session needed)
    booking_command_repo = providers.Factory(BookingCommandRepoImpl)
    event_ticketing_command_repo = providers.Factory(EventTicketingCommandRepoImpl)
    # Query repos still use SQLAlchemy for complex queries
    booking_query_repo = providers.Factory(
        BookingQueryRepoImpl, session_factory=database.provided.session
    )
    event_ticketing_query_repo = providers.Factory(
        EventTicketingQueryRepoImpl, session_factory=database.provided.session
    )
    user_command_repo = providers.Factory(
        UserCommandRepoImpl, session_factory=database.provided.session
    )
    user_query_repo = providers.Factory(
        UserQueryRepoImpl, session_factory=database.provided.session
    )

    # Auth service
    jwt_auth = providers.Singleton(JwtAuth)

    # In-memory Event Broadcaster for SSE (Singleton for shared state)
    booking_event_broadcaster = providers.Singleton(InMemoryEventBroadcasterImpl)

    # Message Queue Publishers
    seat_reservation_mq_publisher = providers.Factory(SeatReservationEventPublisher)
    booking_event_publisher = providers.Factory(BookingEventPublisherImpl)

    # Seat Reservation Domain and Use Cases (CQRS)
    seat_selection_domain = providers.Factory(SeatSelectionDomain)
    seat_state_query_handler = providers.Singleton(SeatStateQueryHandlerImpl)  # Singleton for cache

    # Ticketing Service - Booking Metadata Handler (Kvrocks) - defined here for seat_state_command_handler
    booking_metadata_handler = providers.Singleton(BookingMetadataHandlerImpl)

    seat_state_command_handler = providers.Singleton(
        SeatStateCommandHandlerImpl,
        booking_metadata_handler=booking_metadata_handler,
    )

    # Ticketing Service - Init State Handler
    init_event_and_tickets_state_handler = providers.Factory(
        InitEventAndTicketsStateHandlerImpl,
    )

    # Ticketing Service - Seat Availability Query Handler (Singleton for shared cache)
    seat_availability_query_handler = providers.Singleton(
        SeatAvailabilityQueryHandlerImpl,
    )

    # MQ Infrastructure Orchestrator
    mq_infra_orchestrator = providers.Factory(
        MqInfraOrchestrator,
        kafka_service=kafka_service,
    )

    # Seat Reservation Use Cases
    reserve_seats_use_case = providers.Factory(
        ReserveSeatsUseCase,
        seat_state_handler=seat_state_command_handler,
        mq_publisher=seat_reservation_mq_publisher,
        task_group=task_group,
    )
    release_seat_use_case = providers.Factory(
        ReleaseSeatUseCase,
        seat_state_handler=seat_state_command_handler,
    )
    finalize_seat_payment_use_case = providers.Factory(
        FinalizeSeatPaymentUseCase,
        seat_state_handler=seat_state_command_handler,
    )


container = Container()


def setup():
    container.kafka_service()
    container.config_service()


def cleanup():
    container.reset_singletons()


# FastAPI Dependency Providers (deprecated - use Provide[Container.xxx] instead)
# Keeping these for backward compatibility with existing code
def get_booking_event_publisher():
    """FastAPI dependency provider for booking event publisher."""

    return container.booking_event_publisher()
