"""
https://python-dependency-injector.ets-labs.org/index.html
"""

from dependency_injector import containers, providers
from src.platform.message_queue.subsection_based_partition_strategy import (
    SubSectionBasedPartitionStrategy,
)

from src.platform.config.core_setting import Settings
from src.platform.message_queue.kafka_config_service import KafkaConfigService
from src.service.ticketing.app.command.create_booking_use_case import CreateBookingUseCase
from src.service.ticketing.app.command.create_event_and_tickets_use_case import (
    CreateEventAndTicketsUseCase,
)
from src.service.ticketing.app.command.finalize_seat_payment_use_case import (
    FinalizeSeatPaymentUseCase,
)
from src.service.ticketing.app.command.mock_payment_and_update_booking_status_to_completed_and_ticket_to_paid_use_case import (
    MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase,
)
from src.service.ticketing.app.command.release_seat_use_case import ReleaseSeatUseCase
from src.service.ticketing.app.command.reserve_seats_use_case import ReserveSeatsUseCase
from src.service.ticketing.app.command.update_booking_status_to_cancelled_use_case import (
    UpdateBookingToCancelledUseCase,
)
from src.service.ticketing.app.query.get_booking_use_case import GetBookingUseCase
from src.service.ticketing.app.query.get_event_use_case import GetEventUseCase
from src.service.ticketing.app.query.list_bookings_use_case import ListBookingsUseCase
from src.service.ticketing.app.query.list_events_use_case import ListEventsUseCase
from src.service.ticketing.app.query.user_query_use_case import UserUseCase
from src.service.ticketing.domain.seat_selection_domain import SeatSelectionDomain
from src.service.ticketing.driven_adapter.message_queue.booking_event_publisher_impl import (
    BookingEventPublisherImpl,
)
from src.service.ticketing.driven_adapter.message_queue.mq_infra_orchestrator_impl import (
    MqInfraOrchestrator,
)
from src.service.ticketing.driven_adapter.message_queue.seat_reservation_mq_publisher import (
    SeatReservationEventPublisher,
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
from src.service.ticketing.driven_adapter.state.seat_state_command_handler_impl import (
    SeatStateCommandHandlerImpl,
)
from src.service.ticketing.driven_adapter.state.seat_state_query_handler_impl import (
    SeatStateQueryHandlerImpl,
)
from src.service.ticketing.driving_adapter.http_controller.auth.jwt_auth import JwtAuth


class Container(containers.DeclarativeContainer):
    # Configuration
    config_service = providers.Singleton(Settings)

    # Infrastructure services
    kafka_service = providers.Singleton(KafkaConfigService)
    partition_strategy = providers.Singleton(SubSectionBasedPartitionStrategy)

    # Background task group for fire-and-forget operations (set at startup)
    background_task_group = providers.Object(None)

    # Repositories - ScyllaDB only (Singleton because they are stateless)
    booking_command_repo = providers.Singleton(BookingCommandRepoScyllaImpl)
    booking_query_repo = providers.Singleton(BookingQueryRepoScyllaImpl)
    user_command_repo = providers.Singleton(UserCommandRepoScyllaImpl)
    user_query_repo = providers.Singleton(UserQueryRepoScyllaImpl)
    event_ticketing_command_repo = providers.Singleton(EventTicketingCommandRepoScyllaImpl)
    event_ticketing_query_repo = providers.Singleton(EventTicketingQueryRepoScyllaImpl)

    # Auth service
    jwt_auth = providers.Singleton(JwtAuth)

    # Message Queue Publishers (Singleton because they are stateless)
    seat_reservation_mq_publisher = providers.Singleton(SeatReservationEventPublisher)
    booking_event_publisher = providers.Singleton(BookingEventPublisherImpl)

    # Seat Reservation Domain and Use Cases (CQRS)
    seat_selection_domain = providers.Singleton(SeatSelectionDomain)
    seat_state_query_handler = providers.Singleton(SeatStateQueryHandlerImpl)  # Singleton for cache
    seat_state_command_handler = providers.Singleton(SeatStateCommandHandlerImpl)

    # Ticketing Service - Init State Handler (Singleton because it's stateless)
    init_event_and_tickets_state_handler = providers.Singleton(
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

    # Seat Reservation Use Cases (Singleton because they are stateless)
    reserve_seats_use_case = providers.Singleton(
        ReserveSeatsUseCase,
        seat_state_handler=seat_state_command_handler,
        mq_publisher=seat_reservation_mq_publisher,
    )
    release_seat_use_case = providers.Singleton(
        ReleaseSeatUseCase,
        seat_state_handler=seat_state_command_handler,
    )
    finalize_seat_payment_use_case = providers.Singleton(
        FinalizeSeatPaymentUseCase,
        seat_state_handler=seat_state_command_handler,
    )

    # Ticketing Service - Command Use Cases (Singleton because they are stateless)
    create_booking_use_case = providers.Singleton(
        CreateBookingUseCase,
        booking_command_repo=booking_command_repo,
        event_publisher=booking_event_publisher,
        seat_availability_handler=seat_availability_query_handler,
        background_task_group=background_task_group,
    )
    create_event_and_tickets_use_case = providers.Singleton(
        CreateEventAndTicketsUseCase,
        event_ticketing_command_repo=event_ticketing_command_repo,
        mq_infra_orchestrator=mq_infra_orchestrator,
        init_state_handler=init_event_and_tickets_state_handler,
    )
    update_booking_to_cancelled_use_case = providers.Singleton(
        UpdateBookingToCancelledUseCase,
        booking_command_repo=booking_command_repo,
        event_ticketing_query_repo=event_ticketing_query_repo,
    )
    mock_payment_use_case = providers.Singleton(
        MockPaymentAndUpdateBookingStatusToCompletedAndTicketToPaidUseCase,
        booking_command_repo=booking_command_repo,
    )

    # Ticketing Service - Query Use Cases (Singleton because they are stateless)
    get_booking_use_case = providers.Singleton(
        GetBookingUseCase,
        booking_query_repo=booking_query_repo,
    )
    list_bookings_use_case = providers.Singleton(
        ListBookingsUseCase,
        booking_query_repo=booking_query_repo,
    )
    get_event_use_case = providers.Singleton(
        GetEventUseCase,
        event_ticketing_query_repo=event_ticketing_query_repo,
    )
    list_events_use_case = providers.Singleton(
        ListEventsUseCase,
        event_ticketing_query_repo=event_ticketing_query_repo,
    )
    user_use_case = providers.Singleton(
        UserUseCase,
        user_command_repo=user_command_repo,
        user_query_repo=user_query_repo,
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
