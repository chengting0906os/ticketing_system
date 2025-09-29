"""
https://python-dependency-injector.ets-labs.org/index.html
https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html
"""

from dependency_injector import containers, providers

from src.booking.infra.booking_command_repo_impl import BookingCommandRepoImpl
from src.booking.infra.booking_query_repo_impl import BookingQueryRepoImpl
from src.event_ticketing.infra.event_ticketing_command_repo_impl import (
    EventTicketingCommandRepoImpl,
)
from src.event_ticketing.infra.event_ticketing_query_repo_impl import EventTicketingQueryRepoImpl
from src.shared.config.core_setting import Settings
from src.shared.config.db_setting import Database
from src.shared.message_queue.kafka_config_service import KafkaConfigService
from src.shared.message_queue.section_based_partition_strategy import SectionBasedPartitionStrategy
from src.shared.message_queue.unified_mq_publisher import QuixStreamMqPublisher
from src.shared_kernel.user.infra.user_command_repo_impl import UserCommandRepoImpl
from src.shared_kernel.user.infra.user_query_repo_impl import UserQueryRepoImpl
from src.shared_kernel.user.infra.user_repo_impl import UserRepoImpl
from src.shared_kernel.user.use_case.auth_service import AuthService


class Container(containers.DeclarativeContainer):
    # Configuration
    config_service = providers.Singleton(Settings)

    # Database
    database = providers.Singleton(Database, db_url=config_service.provided.DATABASE_URL_ASYNC)

    # Infrastructure services
    kafka_service = providers.Singleton(KafkaConfigService)
    mq_publisher = providers.Singleton(QuixStreamMqPublisher)
    partition_strategy = providers.Singleton(SectionBasedPartitionStrategy)

    # Repositories - now properly managed with session factory
    booking_command_repo = providers.Factory(
        BookingCommandRepoImpl, session_factory=database.provided.session
    )
    booking_query_repo = providers.Factory(
        BookingQueryRepoImpl, session_factory=database.provided.session
    )
    event_ticketing_command_repo = providers.Factory(
        EventTicketingCommandRepoImpl, session_factory=database.provided.session
    )
    event_ticketing_query_repo = providers.Factory(
        EventTicketingQueryRepoImpl, session_factory=database.provided.session
    )
    user_repo = providers.Factory(UserRepoImpl, session_factory=database.provided.session)
    user_command_repo = providers.Factory(
        UserCommandRepoImpl, session_factory=database.provided.session
    )
    user_query_repo = providers.Factory(
        UserQueryRepoImpl, session_factory=database.provided.session
    )

    # Auth service
    auth_service = providers.Singleton(AuthService)


container = Container()


def setup():
    container.kafka_service()
    container.config_service()
    container.mq_publisher()
    container.partition_strategy()


def cleanup():
    container.reset_singletons()
