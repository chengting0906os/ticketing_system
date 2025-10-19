"""
CDK Stack Unit Tests for Aurora Serverless v2 Infrastructure

Test Category: Unit Testing
Purpose: Verify Aurora stack synthesizes correct CloudFormation resources

Run with: pytest test/deployment/test_aurora_stack.py -v
"""

import aws_cdk as cdk
import aws_cdk.assertions as assertions
import pytest
from aws_cdk import aws_ec2 as ec2

from deployment.cdk.stacks.aurora_stack import AuroraStack


@pytest.fixture
def aurora_stack():
    """
    Aurora stack with VPC for testing.

    Note: VPC and Aurora must be in the same stack to avoid cross-stack references.
    """
    app = cdk.App()

    # Create a single stack containing both VPC and Aurora
    stack = cdk.Stack(
        app,
        'TestAuroraStack',
        env=cdk.Environment(account='123456789012', region='us-west-2'),
    )

    # Create VPC in the same stack
    vpc = ec2.Vpc(stack, 'TestVPC', max_azs=3)

    # Create Aurora stack
    aurora = AuroraStack(
        app,
        'AuroraStack',
        vpc=vpc,
        env=cdk.Environment(account='123456789012', region='us-west-2'),
    )

    return aurora


# ==============================================================================
# Aurora Cluster Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_aurora_cluster_created(aurora_stack):
    """
    Unit: Verify Aurora Serverless v2 cluster is created with correct configuration.

    This tests:
    - Aurora cluster exists
    - PostgreSQL 16.6 engine
    - Serverless v2 scaling (2-64 ACU for 10000 TPS)
    """
    template = assertions.Template.from_stack(aurora_stack)

    # Verify Aurora cluster exists
    template.resource_count_is('AWS::RDS::DBCluster', 1)

    # Verify cluster configuration
    template.has_resource_properties(
        'AWS::RDS::DBCluster',
        {
            'Engine': 'aurora-postgresql',
            'EngineVersion': '16.6',
            'ServerlessV2ScalingConfiguration': {
                'MinCapacity': 2,  # 2 ACU minimum
                'MaxCapacity': 64,  # 64 ACU maximum for 10000 TPS
            },
        },
    )


@pytest.mark.cdk
def test_aurora_instances_created(aurora_stack):
    """
    Unit: Verify 1 writer + 1 reader instances are created.

    This tests:
    - 2 DB instances (1 writer + 1 reader)
    - Both are Serverless v2 instances
    """
    template = assertions.Template.from_stack(aurora_stack)

    # Verify 2 DB instances exist (writer + reader)
    template.resource_count_is('AWS::RDS::DBInstance', 2)

    # Verify instances are db.serverless type
    template.has_resource_properties(
        'AWS::RDS::DBInstance',
        {'DBInstanceClass': 'db.serverless'},
    )


@pytest.mark.cdk
def test_aurora_backup_configuration(aurora_stack):
    """
    Unit: Verify backup configuration for disaster recovery.

    This tests:
    - 7-day backup retention
    - Automated backup enabled
    - Preferred backup window configured
    """
    template = assertions.Template.from_stack(aurora_stack)

    template.has_resource_properties(
        'AWS::RDS::DBCluster',
        {
            'BackupRetentionPeriod': 7,  # 7 days
            'PreferredBackupWindow': '03:00-04:00',  # 3-4 AM UTC
        },
    )


@pytest.mark.cdk
def test_aurora_encryption(aurora_stack):
    """
    Unit: Verify encryption at rest is enabled.

    This tests:
    - Storage encryption enabled
    """
    template = assertions.Template.from_stack(aurora_stack)

    template.has_resource_properties(
        'AWS::RDS::DBCluster',
        {'StorageEncrypted': True},
    )


@pytest.mark.cdk
def test_aurora_deletion_protection(aurora_stack):
    """
    Unit: Verify deletion protection is enabled.

    This tests:
    - Deletion protection enabled (prevents accidental deletion)
    """
    template = assertions.Template.from_stack(aurora_stack)

    template.has_resource_properties(
        'AWS::RDS::DBCluster',
        {'DeletionProtection': True},
    )


# ==============================================================================
# Security Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_aurora_security_group_created(aurora_stack):
    """
    Unit: Verify security group is created for Aurora access.

    This tests:
    - Security group exists
    - PostgreSQL port (5432) ingress rule
    """
    template = assertions.Template.from_stack(aurora_stack)

    # Verify security group exists
    template.resource_count_is('AWS::EC2::SecurityGroup', 1)

    # Verify PostgreSQL port ingress rule
    template.has_resource_properties(
        'AWS::EC2::SecurityGroup',
        {
            'SecurityGroupIngress': assertions.Match.array_with(
                [assertions.Match.object_like({'FromPort': 5432, 'ToPort': 5432})]
            )
        },
    )


@pytest.mark.cdk
def test_aurora_credentials_in_secrets_manager(aurora_stack):
    """
    Unit: Verify database credentials are stored in Secrets Manager.

    This tests:
    - Secret resource created
    - Secret name matches expected pattern
    """
    template = assertions.Template.from_stack(aurora_stack)

    # Verify secret exists
    template.resource_count_is('AWS::SecretsManager::Secret', 1)

    # Verify secret name
    template.has_resource_properties(
        'AWS::SecretsManager::Secret',
        {
            'Name': 'ticketing/aurora/credentials',
        },
    )


# ==============================================================================
# Monitoring Configuration Tests
# ==============================================================================


@pytest.mark.cdk
def test_aurora_performance_insights_enabled(aurora_stack):
    """
    Unit: Verify Performance Insights is enabled for monitoring.

    This tests:
    - Performance Insights enabled on instances
    """
    template = assertions.Template.from_stack(aurora_stack)

    template.has_resource_properties(
        'AWS::RDS::DBInstance',
        {'EnablePerformanceInsights': True},
    )


@pytest.mark.cdk
def test_aurora_cloudwatch_logs_export(aurora_stack):
    """
    Unit: Verify CloudWatch Logs export is configured.

    This tests:
    - PostgreSQL logs exported to CloudWatch
    """
    template = assertions.Template.from_stack(aurora_stack)

    template.has_resource_properties(
        'AWS::RDS::DBCluster',
        {
            'EnableCloudwatchLogsExports': assertions.Match.array_with(
                [assertions.Match.string_like_regexp('.*postgresql.*')]
            )
        },
    )


# ==============================================================================
# CloudFormation Outputs Tests
# ==============================================================================


@pytest.mark.cdk
def test_aurora_outputs_exported(aurora_stack):
    """
    Unit: Verify CloudFormation outputs are exported for other stacks.

    This tests:
    - Writer endpoint exported
    - Reader endpoint exported
    - Secret ARN exported
    - Security Group ID exported
    """
    template = assertions.Template.from_stack(aurora_stack)

    # Verify writer endpoint output
    template.has_output(
        'ClusterEndpoint',
        {'Export': {'Name': 'TicketingAuroraWriterEndpoint'}},
    )

    # Verify reader endpoint output
    template.has_output(
        'ReaderEndpoint',
        {'Export': {'Name': 'TicketingAuroraReaderEndpoint'}},
    )

    # Verify secret ARN output
    template.has_output(
        'SecretArn',
        {'Export': {'Name': 'TicketingAuroraSecretArn'}},
    )

    # Verify security group ID output
    template.has_output(
        'SecurityGroupId',
        {'Export': {'Name': 'TicketingAuroraSecurityGroupId'}},
    )


# ==============================================================================
# Capacity Planning Tests (10000 TPS)
# ==============================================================================


@pytest.mark.cdk
def test_aurora_scaling_for_10000_tps(aurora_stack):
    """
    Unit: Verify Aurora scaling configuration supports 10000 TPS target.

    This tests:
    - Minimum capacity: 2 ACU (~500 TPS idle)
    - Maximum capacity: 64 ACU (~15000+ TPS peak)
    - Capacity range suitable for 10000 TPS workload
    """
    template = assertions.Template.from_stack(aurora_stack)

    template.has_resource_properties(
        'AWS::RDS::DBCluster',
        {
            'ServerlessV2ScalingConfiguration': {
                'MinCapacity': assertions.Match.any_value(),  # Should be >= 2
                'MaxCapacity': assertions.Match.any_value(),  # Should be >= 64
            }
        },
    )

    # Verify actual values
    template.has_resource_properties(
        'AWS::RDS::DBCluster',
        {
            'ServerlessV2ScalingConfiguration': {
                'MinCapacity': 2,
                'MaxCapacity': 64,
            }
        },
    )


if __name__ == '__main__':
    # Allow running directly for quick testing
    pytest.main([__file__, '-v', '--tb=short'])
