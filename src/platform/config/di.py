"""
https://python-dependency-injector.ets-labs.org/index.html
https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html
"""

from dependency_injector import containers, providers

from src.platform.config.core_setting import Settings
from src.platform.database.db_setting import Database
from src.platform.message_queue.kafka_config_service import KafkaConfigService
from src.platform.message_queue.section_based_partition_strategy import (
    SectionBasedPartitionStrategy,
)
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
from src.service.ticketing.driven_adapter.message_queue.mq_infra_orchestrator import (
    MqInfraOrchestrator,
)
from src.service.ticketing.driven_adapter.repo.booking_command_repo_impl import (
    IBookingCommandRepoImpl,
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
from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)
from src.service.ticketing.driving_adapter.http_controller.auth.jwt_auth import AuthService


class Container(containers.DeclarativeContainer):
    # Configuration
    config_service = providers.Singleton(Settings)

    # Database
    database = providers.Singleton(Database, db_url=config_service.provided.DATABASE_URL_ASYNC)

    # Infrastructure services
    kafka_service = providers.Singleton(KafkaConfigService)
    partition_strategy = providers.Singleton(SectionBasedPartitionStrategy)

    # Repositories - session will be injected by use cases
    booking_command_repo = providers.Factory(IBookingCommandRepoImpl)
    booking_query_repo = providers.Factory(
        BookingQueryRepoImpl, session_factory=database.provided.session
    )
    event_ticketing_command_repo = providers.Factory(
        EventTicketingCommandRepoImpl, session_factory=database.provided.session
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
    jwt_auth = providers.Singleton(AuthService)

    # Message Queue Publishers
    seat_reservation_mq_publisher = providers.Factory(SeatReservationEventPublisher)
    booking_event_publisher = providers.Factory(BookingEventPublisherImpl)

    # Seat Reservation Domain and Use Cases (CQRS)
    seat_selection_domain = providers.Factory(SeatSelectionDomain)
    seat_state_query_handler = providers.Factory(SeatStateQueryHandlerImpl)
    seat_state_command_handler = providers.Factory(SeatStateCommandHandlerImpl)

    # Ticketing Service - Init State Handler
    init_event_and_tickets_state_handler = providers.Factory(
        InitEventAndTicketsStateHandlerImpl,
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
    container.partition_strategy()


def cleanup():
    container.reset_singletons()


# FastAPI Dependency Providers
def get_booking_event_publisher():
    """FastAPI dependency provider for booking event publisher."""

    return container.booking_event_publisher()
