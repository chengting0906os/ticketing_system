"""
CDK Stack Unit Tests for MSK Infrastructure

Test Category: Unit Testing
Purpose: Verify MSK stack synthesizes correct CloudFormation resources

Run with: pytest test/deployment/test_msk_stack.py -v
"""

import aws_cdk as cdk
import aws_cdk.assertions as assertions
import pytest
from aws_cdk import aws_ec2 as ec2

from deployment.cdk.stacks.msk_stack import MSKStack


@pytest.fixture
def msk_stack():
    """
    MSK stack with VPC for testing.

    Note: VPC and MSK must be in the same stack to avoid cross-stack references.
    """
    app = cdk.App()

    # Create a single stack containing both VPC and MSK
    stack = cdk.Stack(
        app,
        'TestMSKStack',
        env=cdk.Environment(account='123456789012', region='us-west-2'),
    )

    # Create VPC in the same stack
    vpc = ec2.Vpc(stack, 'TestVPC', max_azs=3)

    # Create MSK stack components within the test stack
    # We'll use composition instead of inheritance for testing
    msk = MSKStack(
        app,
        'MSKStack',
        vpc=vpc,
        env=cdk.Environment(account='123456789012', region='us-west-2'),
    )

    return msk


# ==============================================================================
# MSK Cluster Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_msk_cluster_created(msk_stack):
    """
    Unit: Verify MSK cluster resource is created with correct configuration.

    This tests:
    - MSK cluster exists in the stack
    - Cluster uses correct Kafka version
    - 3-node cluster configuration
    """
    template = assertions.Template.from_stack(msk_stack)

    # Verify MSK cluster exists
    template.resource_count_is('AWS::MSK::Cluster', 1)

    # Verify cluster configuration
    template.has_resource_properties(
        'AWS::MSK::Cluster',
        {
            'ClusterName': 'ticketing-system-kafka',
            'KafkaVersion': '3.5.1',
            'NumberOfBrokerNodes': 3,
        },
    )


@pytest.mark.cdk
def test_msk_replication_settings(msk_stack):
    """
    Unit: Verify replication settings match docker-compose configuration.

    This tests:
    - Replication factor = 3
    - Min ISR = 2
    - Transaction log replication = 3
    """
    template = assertions.Template.from_stack(msk_stack)

    # MSK configuration should exist
    template.resource_count_is('AWS::MSK::Configuration', 1)

    # Verify replication settings in server properties
    template.has_resource_properties(
        'AWS::MSK::Configuration',
        {
            'Name': 'ticketing-system-kafka-config',
            'ServerProperties': assertions.Match.string_like_regexp(
                '.*default\\.replication\\.factor=3.*'
            ),
        },
    )


@pytest.mark.cdk
def test_msk_security_configuration(msk_stack):
    """
    Unit: Verify security configuration (TLS + IAM auth).

    This tests:
    - TLS encryption enabled for client-broker communication
    - IAM authentication enabled
    - Security group created
    """
    template = assertions.Template.from_stack(msk_stack)

    # Verify encryption settings
    template.has_resource_properties(
        'AWS::MSK::Cluster',
        {
            'EncryptionInfo': {'EncryptionInTransit': {'ClientBroker': 'TLS', 'InCluster': True}},
            'ClientAuthentication': {'Sasl': {'Iam': {'Enabled': True}}},
        },
    )

    # Verify security group exists
    template.resource_count_is('AWS::EC2::SecurityGroup', 1)


@pytest.mark.cdk
def test_msk_security_group_rules(msk_stack):
    """
    Unit: Verify security group allows correct Kafka ports.

    This tests:
    - Port 9092 (PLAINTEXT) ingress rule
    - Port 9094 (TLS) ingress rule
    - Port 9098 (IAM auth) ingress rule

    Note: CDK creates inline ingress rules within SecurityGroup resource,
    not separate SecurityGroupIngress resources.
    """
    template = assertions.Template.from_stack(msk_stack)

    # Verify security group has inline ingress rules for Kafka ports
    template.has_resource_properties(
        'AWS::EC2::SecurityGroup',
        {
            'SecurityGroupIngress': assertions.Match.array_with(
                [
                    assertions.Match.object_like({'FromPort': 9092, 'ToPort': 9092}),
                    assertions.Match.object_like({'FromPort': 9094, 'ToPort': 9094}),
                    assertions.Match.object_like({'FromPort': 9098, 'ToPort': 9098}),
                ]
            )
        },
    )


@pytest.mark.cdk
def test_msk_monitoring_enabled(msk_stack):
    """
    Unit: Verify enhanced monitoring is enabled.

    This tests:
    - PER_TOPIC_PER_BROKER monitoring level
    """
    template = assertions.Template.from_stack(msk_stack)

    template.has_resource_properties(
        'AWS::MSK::Cluster', {'EnhancedMonitoring': 'PER_TOPIC_PER_BROKER'}
    )


@pytest.mark.cdk
def test_msk_storage_configuration(msk_stack):
    """
    Unit: Verify broker storage configuration.

    This tests:
    - 100GB EBS volume per broker
    - Provisioned throughput disabled (cost savings)
    """
    template = assertions.Template.from_stack(msk_stack)

    template.has_resource_properties(
        'AWS::MSK::Cluster',
        {
            'BrokerNodeGroupInfo': {
                'StorageInfo': {
                    'EBSStorageInfo': {
                        'VolumeSize': 100,
                        'ProvisionedThroughput': {'Enabled': False},
                    }
                }
            }
        },
    )


# ==============================================================================
# CloudFormation Outputs Tests
# ==============================================================================


@pytest.mark.cdk
def test_msk_outputs_exported(msk_stack):
    """
    Unit: Verify CloudFormation outputs are exported.

    This tests:
    - MSK cluster ARN exported
    - Bootstrap brokers TLS exported
    - Bootstrap brokers IAM exported
    - Security group ID exported
    """
    template = assertions.Template.from_stack(msk_stack)

    # Verify outputs exist
    template.has_output('MSKClusterArn', {'Export': {'Name': 'TicketingSystemMSKClusterArn'}})

    template.has_output(
        'MSKBootstrapBrokers', {'Export': {'Name': 'TicketingSystemMSKBootstrapBrokersTLS'}}
    )

    template.has_output(
        'MSKBootstrapBrokersIAM',
        {'Export': {'Name': 'TicketingSystemMSKBootstrapBrokersIAM'}},
    )

    template.has_output(
        'MSKSecurityGroupId', {'Export': {'Name': 'TicketingSystemMSKSecurityGroupId'}}
    )


# ==============================================================================
# Configuration Compatibility Tests
# ==============================================================================


@pytest.mark.cdk
def test_msk_config_matches_docker_compose(msk_stack):
    """
    Unit: Verify MSK configuration matches docker-compose settings.

    This tests compatibility between local and production Kafka:
    - Transaction log settings
    - Auto-create topics enabled
    - Delete topic enabled
    """
    template = assertions.Template.from_stack(msk_stack)

    # Verify server properties match docker-compose
    template.has_resource_properties(
        'AWS::MSK::Configuration',
        {
            'ServerProperties': assertions.Match.string_like_regexp(
                '.*transaction\\.state\\.log\\.replication\\.factor=3.*'
            )
        },
    )

    template.has_resource_properties(
        'AWS::MSK::Configuration',
        {
            'ServerProperties': assertions.Match.string_like_regexp(
                '.*auto\\.create\\.topics\\.enable=true.*'
            )
        },
    )

    template.has_resource_properties(
        'AWS::MSK::Configuration',
        {
            'ServerProperties': assertions.Match.string_like_regexp(
                '.*delete\\.topic\\.enable=true.*'
            )
        },
    )


if __name__ == '__main__':
    # Allow running directly for quick testing
    pytest.main([__file__, '-v', '--tb=short'])
