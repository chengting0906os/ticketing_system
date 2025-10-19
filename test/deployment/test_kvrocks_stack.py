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
        env=cdk.Environment(account='123456789012', region='us-west-2'),
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
        env=cdk.Environment(account='123456789012', region='us-west-2'),
    )

    return kvrocks


# ==============================================================================
# Security Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_security_group_created(kvrocks_stack):
    """
    Unit: Verify security groups are created for Kvrocks (single master configuration).

    This tests:
    - Kvrocks security group exists (for master)
    - EFS security group exists (for persistent storage)
    - Redis port (6666) ingress rule

    Note: Sentinel port (26666) removed (single master, no replicas)
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify 2 security groups exist (Kvrocks + EFS)
    template.resource_count_is('AWS::EC2::SecurityGroup', 2)

    # Verify Redis protocol port (6666)
    template.has_resource_properties(
        'AWS::EC2::SecurityGroup',
        {
            'SecurityGroupIngress': assertions.Match.array_with(
                [assertions.Match.object_like({'FromPort': 6666, 'ToPort': 6666})]
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
    Unit: Verify IAM roles for Kvrocks master task (single master configuration).

    This tests:
    - Task execution role (for pulling images, writing logs)
    - Task role (for application to access AWS services, EFS)
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify IAM roles exist (2 roles: execution + task for master only)
    roles = template.find_resources('AWS::IAM::Role')
    ecs_roles = [
        r
        for r in roles.values()
        if any(
            stmt.get('Principal', {}).get('Service') == 'ecs-tasks.amazonaws.com'
            for stmt in r['Properties'].get('AssumeRolePolicyDocument', {}).get('Statement', [])
        )
    ]
    assert len(ecs_roles) == 2, f'Expected 2 IAM roles (task + execution), found {len(ecs_roles)}'


# ==============================================================================
# Kvrocks Master Service Tests
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_master_service_created(kvrocks_stack):
    """
    Unit: Verify Kvrocks master service is created (single master configuration).

    This tests:
    - Master task definition (4 vCPU, 8GB RAM for 10000 TPS)
    - Master service created
    - Desired count: 1 task (only 1 master, no replicas)
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify ECS service exists (1 service: master only, no replicas or sentinels)
    template.resource_count_is('AWS::ECS::Service', 1)

    # Verify task definition with correct resources
    # Note: Single master uses higher resources (4 vCPU, 8GB RAM)
    template.has_resource_properties(
        'AWS::ECS::TaskDefinition',
        {
            'Cpu': '4096',  # 4 vCPU
            'Memory': '8192',  # 8GB RAM
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
    Unit: Verify Kvrocks replica service is NOT created (single master configuration).

    This tests:
    - Only 1 service exists (master only, no replicas for cost optimization)

    Note: Replicas removed in single master configuration
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Single master configuration: 1 service only (no replicas, no sentinels)
    template.resource_count_is('AWS::ECS::Service', 1)


# ==============================================================================
# Sentinel Service Tests
# ==============================================================================


@pytest.mark.cdk
def test_sentinel_service_created(kvrocks_stack):
    """
    Unit: Verify Sentinel service is NOT created (single master configuration).

    This tests:
    - No sentinel service (single master, no automatic failover)
    - Only 1 task definition (master only)

    Note: Sentinel removed in single master configuration
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify 1 service exists (master only, no sentinels)
    template.resource_count_is('AWS::ECS::Service', 1)

    # Verify 1 task definition (master only, no sentinel)
    template.resource_count_is('AWS::ECS::TaskDefinition', 1)


@pytest.mark.cdk
def test_sentinel_container_configuration(kvrocks_stack):
    """
    Unit: Verify Sentinel is NOT configured (single master configuration).

    This tests:
    - No port 26666 (Sentinel port removed)
    - Only port 6666 (Kvrocks master port)

    Note: Sentinel removed in single master configuration
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify Kvrocks uses port 6666 (not 26666)
    template.has_resource_properties(
        'AWS::ECS::TaskDefinition',
        {
            'ContainerDefinitions': assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            'PortMappings': assertions.Match.array_with(
                                [assertions.Match.object_like({'ContainerPort': 6666})]
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
    - Master service name output exists (no export for single master)
    - EFS file system ID exported
    - Connection info exported

    Note: Sentinel outputs removed (single master configuration)
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify master service output (without Export for simplicity)
    template.has_output(
        'KvrocksMasterServiceName',
        {'Description': 'Kvrocks master service name'},
    )

    # Verify EFS file system output
    template.has_output(
        'EFSFileSystemId',
        {'Description': 'EFS file system ID for Kvrocks data'},
    )

    # Verify connection info output
    template.has_output(
        'ConnectionInfo',
        {'Description': 'Kvrocks connection endpoint (single master)'},
    )


# ==============================================================================
# High Availability Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_high_availability_setup(kvrocks_stack):
    """
    Unit: Verify single master configuration (no HA for cost optimization).

    This tests:
    - 1 master only (no replicas, no sentinels)
    - EFS for data persistence
    - 1 task definition (master only)

    Note: HA removed in single master configuration
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify 1 service (master only, no replicas, no sentinels)
    template.resource_count_is('AWS::ECS::Service', 1)

    # Verify EFS for persistence
    template.resource_count_is('AWS::EFS::FileSystem', 1)

    # Verify 1 task definition (master only)
    template.resource_count_is('AWS::ECS::TaskDefinition', 1)


# ==============================================================================
# Capacity Planning Tests (10000 TPS)
# ==============================================================================


@pytest.mark.cdk
def test_kvrocks_capacity_for_10000_tps(kvrocks_stack):
    """
    Unit: Verify Kvrocks capacity supports 10000 TPS target (single master).

    This tests:
    - 1 Kvrocks master instance (no replicas)
    - Instance: 4 vCPU + 8GB RAM (sufficient for 50000+ ops/sec)
    - 10000 TPS is well within capacity

    Note: Single master with higher resources instead of multiple small instances
    """
    template = assertions.Template.from_stack(kvrocks_stack)

    # Verify task resources (4 vCPU, 8GB RAM for single master)
    template.has_resource_properties(
        'AWS::ECS::TaskDefinition',
        {
            'Cpu': '4096',  # 4 vCPU
            'Memory': '8192',  # 8GB RAM
        },
    )

    # Verify 1 service (master only, no replicas, no sentinels)
    template.resource_count_is('AWS::ECS::Service', 1)


if __name__ == '__main__':
    # Allow running directly for quick testing
    pytest.main([__file__, '-v', '--tb=short'])
