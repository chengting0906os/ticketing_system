"""
https://python-dependency-injector.ets-labs.org/index.html
"""

from dependency_injector import containers, providers

from src.booking.infra.booking_command_repo_impl import BookingCommandRepoImpl
from src.booking.infra.booking_query_repo_impl import BookingQueryRepoImpl
from src.event_ticketing.infra.event_ticketing_command_repo_impl import (
    EventTicketingCommandRepoImpl,
)
from src.event_ticketing.infra.event_ticketing_query_repo_impl import EventTicketingQueryRepoImpl
from src.shared.config.core_setting import Settings
from src.shared.message_queue.kafka_config_service import KafkaConfigService
from src.shared.message_queue.section_based_partition_strategy import SectionBasedPartitionStrategy
from src.shared.message_queue.unified_mq_publisher import QuixStreamMqPublisher
from src.shared_kernel.user.infra.user_command_repo_impl import UserCommandRepoImpl
from src.shared_kernel.user.infra.user_query_repo_impl import UserQueryRepoImpl
from src.shared_kernel.user.infra.user_repo_impl import UserRepoImpl


class Container(containers.DeclarativeContainer):
    config_service = providers.Singleton(Settings)
    kafka_service = providers.Singleton(KafkaConfigService)
    mq_publisher = providers.Singleton(QuixStreamMqPublisher)
    partition_strategy = providers.Singleton(SectionBasedPartitionStrategy)
    #
    booking_command_repo = providers.Singleton(BookingCommandRepoImpl)
    booking_query_repo = providers.Singleton(BookingQueryRepoImpl)
    event_ticketing_command_repo = providers.Singleton(EventTicketingCommandRepoImpl)
    event_ticketing_query_repo = providers.Singleton(EventTicketingQueryRepoImpl)
    user_repo = providers.Singleton(UserRepoImpl)
    user_command_repo = providers.Singleton(UserCommandRepoImpl)
    user_query_repo = providers.Singleton(UserQueryRepoImpl)


container = Container()


def setup():
    container.kafka_service()
    container.config_service()
    container.mq_publisher()
    container.partition_strategy()


def cleanup():
    container.reset_singletons()
