"""
https://python-dependency-injector.ets-labs.org/index.html
https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html
"""

from dependency_injector import containers, providers
from src.service.reservation.app.command.release_seat_use_case import ReleaseSeatUseCase
from src.service.reservation.app.command.reserve_seats_use_case import ReserveSeatsUseCase
from src.service.reservation.driven_adapter.state.reservation_helper.atomic_release_executor import (
    AtomicReleaseExecutor,
)
from src.service.reservation.driven_adapter.state.reservation_helper.atomic_reservation_executor import (
    AtomicReservationExecutor,
)
from src.service.reservation.driven_adapter.repo.booking_command_repo_impl import (
    BookingCommandRepoImpl as ReservationBookingCommandRepoImpl,
)
from src.service.reservation.driven_adapter.state.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)
from src.service.reservation.driven_adapter.state.seat_state_query_handler_impl import (
    SeatStateQueryHandlerImpl,
)

from src.platform.config.core_setting import Settings
from src.platform.database.db_setting import Database
from src.platform.state.kvrocks_client import kvrocks_client
from src.service.shared_kernel.driven_adapter.event_stats_query_repo_impl import (
    EventStatsQueryRepoImpl,
)
from src.service.shared_kernel.driven_adapter.pubsub_handler_impl import (
    PubSubHandlerImpl,
)
from src.platform.message_queue.kafka_config_service import KafkaConfigService
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
from src.service.ticketing.app.interface.i_booking_event_publisher import IBookingEventPublisher


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

    # Repositories (stateless - use session_factory per-request)
    booking_command_repo = providers.Singleton(BookingCommandRepoImpl)
    event_ticketing_command_repo = providers.Singleton(EventTicketingCommandRepoImpl)
    booking_query_repo = providers.Singleton(
        BookingQueryRepoImpl, session_factory=database.provided.session
    )
    event_ticketing_query_repo = providers.Singleton(
        EventTicketingQueryRepoImpl, session_factory=database.provided.session
    )
    user_command_repo = providers.Singleton(
        UserCommandRepoImpl, session_factory=database.provided.session
    )
    user_query_repo = providers.Singleton(
        UserQueryRepoImpl, session_factory=database.provided.session
    )

    # Auth service
    jwt_auth = providers.Singleton(JwtAuth)

    # Event Stats Query Repo (for throttled broadcast)
    event_stats_query_repo = providers.Singleton(EventStatsQueryRepoImpl)

    # Kvrocks Pub/Sub Handler for SSE (distributed pub/sub)
    # Uses throttle pattern: schedule_stats_broadcast() triggers 1s delayed query+broadcast
    pubsub_handler: providers.Provider[PubSubHandlerImpl] = providers.Singleton(
        PubSubHandlerImpl,
        redis_client=providers.Factory(kvrocks_client.get_client),
        event_stats_query_repo=event_stats_query_repo,
    )

    # Message Queue Publishers
    booking_event_publisher = providers.Singleton(BookingEventPublisherImpl)

    # Reservation Service - Booking Command Repo (PostgreSQL writes)
    reservation_booking_command_repo = providers.Singleton(ReservationBookingCommandRepoImpl)

    # Seat Reservation Use Cases (CQRS)
    seat_state_query_handler = providers.Singleton(SeatStateQueryHandlerImpl)  # Singleton for cache

    # Ticketing Service - Booking Metadata Handler (Kvrocks) - defined here for seat_state_command_handler
    booking_metadata_handler = providers.Singleton(BookingMetadataHandlerImpl)

    # Seat Reservation Executors (with idempotency via booking_metadata_handler)
    atomic_reservation_executor = providers.Singleton(
        AtomicReservationExecutor,
        booking_metadata_handler=booking_metadata_handler,
    )
    atomic_release_executor = providers.Singleton(
        AtomicReleaseExecutor,
        booking_metadata_handler=booking_metadata_handler,
    )

    seat_state_command_handler = providers.Singleton(
        SeatStateCommandHandlerImpl,
        reservation_executor=atomic_reservation_executor,
        release_executor=atomic_release_executor,
    )

    # Ticketing Service - Init State Handler
    init_event_and_tickets_state_handler = providers.Singleton(InitEventAndTicketsStateHandlerImpl)

    # Ticketing Service - Seat Availability Query Handler (updated via Redis Pub/Sub)
    seat_availability_query_handler = providers.Singleton(
        SeatAvailabilityQueryHandlerImpl,
        ttl_seconds=10.0,
    )

    # MQ Infrastructure Orchestrator
    mq_infra_orchestrator = providers.Singleton(
        MqInfraOrchestrator,
        kafka_service=kafka_service,
    )

    # Seat Reservation Use Cases (stateless, can be Singleton)
    reserve_seats_use_case = providers.Singleton(
        ReserveSeatsUseCase,
        seat_state_handler=seat_state_command_handler,
        booking_command_repo=reservation_booking_command_repo,
        pubsub_handler=pubsub_handler,
    )
    release_seat_use_case = providers.Singleton(
        ReleaseSeatUseCase,
        seat_state_handler=seat_state_command_handler,
        booking_command_repo=reservation_booking_command_repo,
        pubsub_handler=pubsub_handler,
    )


container = Container()


def setup() -> None:
    container.kafka_service()
    container.config_service()


def cleanup() -> None:
    container.reset_singletons()


# FastAPI Dependency Providers (deprecated - use Provide[Container.xxx] instead)
# Keeping these for backward compatibility with existing code
def get_booking_event_publisher() -> IBookingEventPublisher:
    """FastAPI dependency provider for booking event publisher."""

    return container.booking_event_publisher()
