"""
https://python-dependency-injector.ets-labs.org/index.html
"""

from dependency_injector import containers, providers

from src.platform.config.core_setting import Settings
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
from src.service.ticketing.driven_adapter.message_queue.mq_infra_orchestrator_impl import (
    MqInfraOrchestrator,
)

# ScyllaDB Repositories
from src.service.ticketing.driven_adapter.repo.booking_command_repo_scylla_impl import (
    BookingCommandRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.repo.booking_query_repo_scylla_impl import (
    BookingQueryRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.repo.event_ticketing_command_repo_scylla_impl import (
    EventTicketingCommandRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.repo.event_ticketing_query_repo_scylla_impl import (
    EventTicketingQueryRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.repo.user_command_repo_scylla_impl import (
    UserCommandRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.repo.user_query_repo_scylla_impl import (
    UserQueryRepoScyllaImpl,
)
from src.service.ticketing.driven_adapter.state.init_event_and_tickets_state_handler_impl import (
    InitEventAndTicketsStateHandlerImpl,
)
from src.service.ticketing.driven_adapter.state.seat_availability_query_handler_impl import (
    SeatAvailabilityQueryHandlerImpl,
)
from src.service.ticketing.driving_adapter.http_controller.auth.jwt_auth import JwtAuth


class Container(containers.DeclarativeContainer):
    # Configuration
    config_service = providers.Singleton(Settings)

    # Infrastructure services
    kafka_service = providers.Singleton(KafkaConfigService)
    partition_strategy = providers.Singleton(SectionBasedPartitionStrategy)

    # Repositories - ScyllaDB only
    booking_command_repo = providers.Factory(BookingCommandRepoScyllaImpl)
    booking_query_repo = providers.Factory(BookingQueryRepoScyllaImpl)
    user_command_repo = providers.Factory(UserCommandRepoScyllaImpl)
    user_query_repo = providers.Factory(UserQueryRepoScyllaImpl)
    event_ticketing_command_repo = providers.Factory(EventTicketingCommandRepoScyllaImpl)
    event_ticketing_query_repo = providers.Factory(EventTicketingQueryRepoScyllaImpl)

    # Auth service
    jwt_auth = providers.Singleton(JwtAuth)

    # Message Queue Publishers
    seat_reservation_mq_publisher = providers.Factory(SeatReservationEventPublisher)
    booking_event_publisher = providers.Factory(BookingEventPublisherImpl)

    # Seat Reservation Domain and Use Cases (CQRS)
    seat_selection_domain = providers.Factory(SeatSelectionDomain)
    seat_state_query_handler = providers.Singleton(SeatStateQueryHandlerImpl)  # Singleton for cache
    seat_state_command_handler = providers.Factory(SeatStateCommandHandlerImpl)

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


# FastAPI Dependency Providers (deprecated - use Provide[Container.xxx] instead)
# Keeping these for backward compatibility with existing code
def get_booking_event_publisher():
    """FastAPI dependency provider for booking event publisher."""

    return container.booking_event_publisher()
