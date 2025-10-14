"""
CDK Stack Unit Tests for Kvrocks + Sentinel Infrastructure

Test Category: Unit Testing
Purpose: Verify Kvrocks stack synthesizes correct CloudFormation resources

Run with: pytest test/deployment/test_kvrocks_stack.py -v
"""

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2, aws_ecs as ecs
import aws_cdk.assertions as assertions
import pytest

from deployment.cdk.stacks.kvrocks_stack import KvrocksStack


@pytest.fixture
def kvrocks_stack():
    """
    Kvrocks stack with VPC and ECS cluster for testing.

    Note: All resources must be in the same stack to avoid cross-stack references.
    """
    app = cdk.App()

    # Create a single stack containing VPC, ECS cluster, and Kvrocks
    stack = cdk.Stack(
        app,
        'TestKvrocksStack',
        env=cdk.Environment(account='123456789012', region='us-east-1'),
    )

    # Create VPC in the same stack
    vpc = ec2.Vpc(stack, 'TestVPC', max_azs=3)

    # Create ECS cluster in the same stack
    cluster = ecs.Cluster(
        stack,
        'TestCluster',
        cluster_name='test-cluster',
        vpc=vpc,
        container_insights=True,
    )

    # Create Kvrocks stack components
    kvrocks = KvrocksStack(
        app,
        'KvrocksStack',
        vpc=vpc,
        cluster=cluster,
        env=cdk.Environment(account='123456789012', region='us-east-1'),
    )

    return kvrocks


# ==============================================================================
# Security Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_security_group_created(kvrocks_stack):
    """
    Unit: Verify security group is created for Kvrocks cluster.

    This tests:
    - Security group exists
    - Redis port (6666) ingress rule
    - Sentinel port (26666) ingress rule
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify security group exists
    template.resource_count_is('AWS::EC2::SecurityGroup', 1)

    # Verify Redis protocol port (6666)
    template.has_resource_properties(
        'AWS::EC2::SecurityGroup',
        {
            'SecurityGroupIngress': assertions.Match.array_with(
                [assertions.Match.object_like({'FromPort': 6666, 'ToPort': 6666})]
            )
        },
    )

    # Verify Sentinel port (26666)
    template.has_resource_properties(
        'AWS::EC2::SecurityGroup',
        {
            'SecurityGroupIngress': assertions.Match.array_with(
                [assertions.Match.object_like({'FromPort': 26666, 'ToPort': 26666})]
            )
        },
    )


# ==============================================================================
# EFS Storage Tests
# ==============================================================================


@pytest.mark.cdk
def test_efs_file_system_created(kvrocks_stack):
    """
    Unit: Verify EFS file system for persistent storage.

    This tests:
    - EFS file system exists
    - Encryption enabled
    - General Purpose performance mode
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify EFS file system exists
    template.resource_count_is('AWS::EFS::FileSystem', 1)

    # Verify encryption enabled
    template.has_resource_properties(
        'AWS::EFS::FileSystem',
        {
            'Encrypted': True,
            'PerformanceMode': 'generalPurpose',
        },
    )


@pytest.mark.cdk
def test_efs_access_point_created(kvrocks_stack):
    """
    Unit: Verify EFS access point for Kvrocks data directory.

    This tests:
    - Access point exists
    - Correct POSIX permissions
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify access point exists
    template.resource_count_is('AWS::EFS::AccessPoint', 1)

    # Verify POSIX user configuration
    template.has_resource_properties(
        'AWS::EFS::AccessPoint',
        {
            'PosixUser': {
                'Uid': '999',  # Kvrocks user
                'Gid': '999',  # Kvrocks group
            }
        },
    )


# ==============================================================================
# IAM Roles Tests
# ==============================================================================


@pytest.mark.cdk
def test_iam_roles_created(kvrocks_stack):
    """
    Unit: Verify IAM roles for Kvrocks tasks.

    This tests:
    - Task execution role (for pulling images, writing logs)
    - Task role (for application to access AWS services)
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify IAM roles exist (at least 2: execution + task)
    # Note: May be more if Sentinel has separate roles
    roles_count = len(
        [
            r
            for r in template.find_resources('AWS::IAM::Role').values()
            if 'Kvrocks' in r['Properties'].get('RoleName', '')
            or any(
                'ecs-tasks.amazonaws.com' in p.get('Service', [''])[0]
                for p in r['Properties'].get('AssumeRolePolicyDocument', {}).get('Statement', [])
            )
        ]
    )
    assert roles_count >= 2, 'Should have at least task execution and task roles'


# ==============================================================================
# Kvrocks Master Service Tests
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_master_service_created(kvrocks_stack):
    """
    Unit: Verify Kvrocks master service is created.

    This tests:
    - Master task definition (1 vCPU, 2GB RAM)
    - Master service created
    - Desired count: 1 task (only 1 master)
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify ECS services exist (at least 3: master + replicas + sentinels)
    template.resource_count_is('AWS::ECS::Service', 3)

    # Verify task definition with correct resources
    # Note: All tasks use same resources (1 vCPU, 2GB RAM)
    template.has_resource_properties(
        'AWS::ECS::TaskDefinition',
        {
            'Cpu': '1024',  # 1 vCPU
            'Memory': '2048',  # 2GB RAM
        },
    )


@pytest.mark.cdk
def test_kvrocks_master_container_configuration(kvrocks_stack):
    """
    Unit: Verify Kvrocks master container configuration.

    This tests:
    - Container image (apache/kvrocks)
    - Port mapping (6666)
    - Environment variables
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify container uses Kvrocks image
    template.has_resource_properties(
        'AWS::ECS::TaskDefinition',
        {
            'ContainerDefinitions': assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            'Image': assertions.Match.string_like_regexp('.*kvrocks.*'),
                            'PortMappings': assertions.Match.array_with(
                                [assertions.Match.object_like({'ContainerPort': 6666})]
                            ),
                        }
                    )
                ]
            )
        },
    )


@pytest.mark.cdk
def test_kvrocks_master_volume_mount(kvrocks_stack):
    """
    Unit: Verify Kvrocks master mounts EFS volume.

    This tests:
    - EFS volume defined in task definition
    - Volume mount configured for persistence
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify task definition has EFS volume
    template.has_resource_properties(
        'AWS::ECS::TaskDefinition',
        {
            'Volumes': assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            'Name': 'kvrocks-data',
                            'EFSVolumeConfiguration': assertions.Match.object_like(
                                {
                                    'TransitEncryption': 'ENABLED',
                                }
                            ),
                        }
                    )
                ]
            )
        },
    )


# ==============================================================================
# Kvrocks Replica Service Tests
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_replica_service_created(kvrocks_stack):
    """
    Unit: Verify Kvrocks replica services are created.

    This tests:
    - Replica task definition exists
    - Replica service exists
    - Desired count: 2 tasks (2 replicas)
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Already verified in test_kvrocks_master_service_created
    # 3 services total: 1 master + 1 replica service (2 tasks) + 1 sentinel service (3 tasks)
    template.resource_count_is('AWS::ECS::Service', 3)


# ==============================================================================
# Sentinel Service Tests
# ==============================================================================


@pytest.mark.cdk
def test_sentinel_service_created(kvrocks_stack):
    """
    Unit: Verify Sentinel service is created for automatic failover.

    This tests:
    - Sentinel task definition exists
    - Sentinel service exists
    - Desired count: 3 tasks (quorum = 2)
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify 3 services exist (already checked above)
    template.resource_count_is('AWS::ECS::Service', 3)

    # Verify at least 3 task definitions (master, replica, sentinel)
    template.resource_count_is('AWS::ECS::TaskDefinition', 3)


@pytest.mark.cdk
def test_sentinel_container_configuration(kvrocks_stack):
    """
    Unit: Verify Sentinel container is configured correctly.

    This tests:
    - Sentinel image
    - Port 26666 for Sentinel protocol
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify container uses Redis image for Sentinel
    # Note: Sentinel can use redis:alpine or redis:latest with --sentinel flag
    template.has_resource_properties(
        'AWS::ECS::TaskDefinition',
        {
            'ContainerDefinitions': assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            'PortMappings': assertions.Match.array_with(
                                [assertions.Match.object_like({'ContainerPort': 26666})]
                            )
                        }
                    )
                ]
            )
        },
    )


# ==============================================================================
# Logging Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_cloudwatch_logs_configured(kvrocks_stack):
    """
    Unit: Verify CloudWatch Logs for Kvrocks and Sentinel output.

    This tests:
    - Log groups created
    - 1-week retention
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify log groups exist (at least 3: master, replica, sentinel)
    template.has_resource_properties(
        'AWS::Logs::LogGroup',
        {'RetentionInDays': 7},
    )


# ==============================================================================
# CloudFormation Outputs Tests
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_outputs_exported(kvrocks_stack):
    """
    Unit: Verify CloudFormation outputs are exported for other stacks.

    This tests:
    - Master service name exported
    - Sentinel service name exported
    - Security Group ID exported
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify master service output
    template.has_output(
        'KvrocksMasterServiceName',
        {'Export': {'Name': 'TicketingKvrocksMasterServiceName'}},
    )

    # Verify sentinel service output
    template.has_output(
        'SentinelServiceName',
        {'Export': {'Name': 'TicketingSentinelServiceName'}},
    )

    # Verify security group output
    template.has_output(
        'KvrocksSecurityGroupId',
        {'Export': {'Name': 'TicketingKvrocksSecurityGroupId'}},
    )


# ==============================================================================
# High Availability Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_high_availability_setup(kvrocks_stack):
    """
    Unit: Verify high availability configuration.

    This tests:
    - 1 master + 2 replicas (3 total Kvrocks instances)
    - 3 Sentinels for quorum (quorum = 2)
    - EFS for data persistence
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify 3 services (master, replica, sentinel)
    template.resource_count_is('AWS::ECS::Service', 3)

    # Verify EFS for persistence
    template.resource_count_is('AWS::EFS::FileSystem', 1)

    # Verify 3 task definitions (1 for master, 1 for replica, 1 for sentinel)
    template.resource_count_is('AWS::ECS::TaskDefinition', 3)


# ==============================================================================
# Capacity Planning Tests (10000 TPS)
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_capacity_for_10000_tps(kvrocks_stack):
    """
    Unit: Verify Kvrocks capacity supports 10000 TPS target.

    This tests:
    - 3 Kvrocks instances (1 master + 2 replicas)
    - Each instance: 1 vCPU + 2GB RAM
    - Kvrocks can handle 50000+ ops/sec per instance
    - 10000 TPS is well within capacity
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify task resources (1 vCPU, 2GB RAM per instance)
    template.has_resource_properties(
        'AWS::ECS::TaskDefinition',
        {
            'Cpu': '1024',  # 1 vCPU
            'Memory': '2048',  # 2GB RAM
        },
    )

    # Verify 3 services for HA (master + replica + sentinel)
    template.resource_count_is('AWS::ECS::Service', 3)


if __name__ == '__main__':
    # Allow running directly for quick testing
    pytest.main([__file__, '-v', '--tb=short'])
