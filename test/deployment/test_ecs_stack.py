"""
Tests for ECS Fargate Stack

Validates:
- ECS cluster configuration
- Fargate service with auto-scaling
- Application Load Balancer
- CloudWatch alarms
- ECR repository

NOTE: These tests use isolated VPC and KVRocks stacks to avoid
cross-stack dependencies. The production deployment uses VpcStack
for shared network resources
"""

import aws_cdk as cdk
import aws_cdk.assertions as assertions
import pytest
from aws_cdk import aws_ec2 as ec2

from deployment.cdk.stacks.ecs_stack import EcsStack
from deployment.cdk.stacks.kvrocks_stack import KVRocksStack


@pytest.mark.deployment
class TestEcsStack:
    """Test ECS Fargate stack for 10K QPS"""

    @pytest.fixture
    def test_infrastructure(self):
        """Create minimal test infrastructure for ECS stack

        Creates a standalone VPC and KVRocks cluster without Aurora
        to avoid cyclic dependencies in unit tests.
        """
        app = cdk.App()

        # Create a simple test stack for shared resources
        test_stack = cdk.Stack(
            app,
            'TestInfraStack',
            env=cdk.Environment(account='123456789012', region='us-east-1'),
        )

        # Create standalone VPC
        vpc = ec2.Vpc(
            test_stack,
            'TestVpc',
            max_azs=2,
        )

        # Create app security group
        app_sg = ec2.SecurityGroup(
            test_stack,
            'TestAppSG',
            vpc=vpc,
            description='Test security group for ECS',
        )

        # Create test secret
        test_secret = cdk.aws_secretsmanager.Secret(
            test_stack,
            'TestDbSecret',
            secret_name='test-db-secret',
            generate_secret_string=cdk.aws_secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "test"}',
                generate_string_key='password',
            ),
        )

        # Create KVRocks stack
        kvrocks_stack = KVRocksStack(
            app,
            'TestKVRocksStack',
            vpc=vpc,
            app_security_group_id=app_sg.security_group_id,
            environment='production',
            env=cdk.Environment(account='123456789012', region='us-east-1'),
        )

        return {
            'app': app,
            'vpc': vpc,
            'app_security_group': app_sg,
            'kvrocks_cluster': kvrocks_stack.cluster,
            'kvrocks_endpoint': kvrocks_stack.connection_string,
            'db_secret': test_secret,
        }

    @pytest.fixture
    def production_ecs_stack(self, test_infrastructure):
        """Create production ECS stack for testing"""
        infra = test_infrastructure

        stack = EcsStack(
            infra['app'],
            'TestEcsStack',
            vpc=infra['vpc'],
            cluster=infra['kvrocks_cluster'],
            app_security_group_id=infra['app_security_group'].security_group_id,
            db_credentials_secret=infra['db_secret'],
            db_proxy_endpoint='test-proxy.rds.amazonaws.com',
            db_reader_endpoint='test-reader.rds.amazonaws.com',
            kvrocks_endpoint=infra['kvrocks_endpoint'],
            environment='production',
            env=cdk.Environment(account='123456789012', region='us-east-1'),
        )
        return stack

    def test_ecs_cluster_exists(self, production_ecs_stack):
        """Test that ECS cluster is used (imported from KVRocks stack)"""
        # The cluster is passed in from KVRocksStack, not created by EcsStack
        # Verify that the stack stores the cluster reference
        assert production_ecs_stack.cluster is not None
        assert production_ecs_stack.cluster.cluster_name is not None

    def test_fargate_service_exists(self, production_ecs_stack):
        """Test that Fargate service is created"""
        template = assertions.Template.from_stack(production_ecs_stack)

        template.has_resource_properties(
            'AWS::ECS::Service',
            {
                'LaunchType': 'FARGATE',
            },
        )

    def test_production_has_high_desired_count(self, production_ecs_stack):
        """Test that production starts with 30 tasks"""
        template = assertions.Template.from_stack(production_ecs_stack)

        template.has_resource_properties(
            'AWS::ECS::Service',
            {
                'DesiredCount': 30,
            },
        )

    def test_task_definition_configured(self, production_ecs_stack):
        """Test that task definition has correct CPU and memory"""
        template = assertions.Template.from_stack(production_ecs_stack)

        # Production: 0.5 vCPU (512) and 1GB (1024)
        template.has_resource_properties(
            'AWS::ECS::TaskDefinition',
            {
                'Cpu': '512',
                'Memory': '1024',
                'NetworkMode': 'awsvpc',
                'RequiresCompatibilities': ['FARGATE'],
            },
        )

    def test_container_environment_variables(self, production_ecs_stack):
        """Test that container has necessary environment variables"""
        template = assertions.Template.from_stack(production_ecs_stack)

        # Find task definition
        task_defs = template.find_resources('AWS::ECS::TaskDefinition')
        assert len(task_defs) > 0, 'Should have task definition'

        # Check first task definition
        task_def = list(task_defs.values())[0]
        container_defs = task_def['Properties']['ContainerDefinitions']

        # Should have at least one container
        assert len(container_defs) > 0, 'Should have container definition'

        # Check environment variables (match actual implementation)
        env_vars = container_defs[0].get('Environment', [])
        env_var_names = {var['Name'] for var in env_vars}

        # Verify actual environment variable names from ECS stack implementation
        assert 'ENVIRONMENT' in env_var_names
        assert 'POSTGRES_SERVER' in env_var_names  # Writer endpoint
        assert 'POSTGRES_READ_SERVER' in env_var_names  # Reader endpoint
        assert 'KVROCKS_HOST' in env_var_names
        assert 'WORKERS' in env_var_names

    def test_container_secrets_configured(self, production_ecs_stack):
        """Test that container uses Secrets Manager for credentials"""
        template = assertions.Template.from_stack(production_ecs_stack)

        # Find task definition
        task_defs = template.find_resources('AWS::ECS::TaskDefinition')
        task_def = list(task_defs.values())[0]
        container_defs = task_def['Properties']['ContainerDefinitions']

        # Check secrets
        secrets = container_defs[0].get('Secrets', [])
        secret_names = {secret['Name'] for secret in secrets}

        assert 'DB_PASSWORD' in secret_names
        assert 'DB_USERNAME' in secret_names

    def test_health_check_configured(self, production_ecs_stack):
        """Test that container has health check"""
        template = assertions.Template.from_stack(production_ecs_stack)

        task_defs = template.find_resources('AWS::ECS::TaskDefinition')
        task_def = list(task_defs.values())[0]
        container_defs = task_def['Properties']['ContainerDefinitions']

        # Should have health check
        health_check = container_defs[0].get('HealthCheck')
        assert health_check is not None, 'Container should have health check'

    def test_load_balancer_exists(self, production_ecs_stack):
        """Test that Application Load Balancer is created"""
        template = assertions.Template.from_stack(production_ecs_stack)

        template.has_resource_properties(
            'AWS::ElasticLoadBalancingV2::LoadBalancer',
            {
                'Type': 'application',
                'Scheme': 'internet-facing',
            },
        )

    def test_target_group_health_check(self, production_ecs_stack):
        """Test that target group has health check configured"""
        template = assertions.Template.from_stack(production_ecs_stack)

        # CDK sets HealthCheckProtocol implicitly, so only check explicit properties
        template.has_resource_properties(
            'AWS::ElasticLoadBalancingV2::TargetGroup',
            {
                'HealthCheckPath': '/health',
                'HealthCheckIntervalSeconds': 30,
                'HealthCheckTimeoutSeconds': 5,
                'HealthyThresholdCount': 2,
                'UnhealthyThresholdCount': 3,
            },
        )

    def test_auto_scaling_configured(self, production_ecs_stack):
        """Test that auto-scaling is configured"""
        template = assertions.Template.from_stack(production_ecs_stack)

        # Should have scalable target
        template.has_resource_properties(
            'AWS::ApplicationAutoScaling::ScalableTarget',
            {
                'MinCapacity': 30,
                'MaxCapacity': 100,
                'ServiceNamespace': 'ecs',
            },
        )

        # Should have scaling policies
        scaling_policies = template.find_resources('AWS::ApplicationAutoScaling::ScalingPolicy')
        assert len(scaling_policies) >= 2, 'Should have at least 2 scaling policies'

    def test_cloudwatch_alarms_created(self, production_ecs_stack):
        """Test that CloudWatch alarms are created"""
        template = assertions.Template.from_stack(production_ecs_stack)

        alarms = template.find_resources('AWS::CloudWatch::Alarm')

        # Should have CPU, memory, unhealthy targets, response time alarms
        assert len(alarms) >= 4, 'Should have at least 4 CloudWatch alarms'

    def test_ecr_repository_created(self, production_ecs_stack):
        """Test that ECR repository is created"""
        template = assertions.Template.from_stack(production_ecs_stack)

        template.has_resource_properties(
            'AWS::ECR::Repository',
            {
                'ImageScanningConfiguration': {
                    'ScanOnPush': True,
                },
            },
        )

    def test_iam_roles_configured(self, production_ecs_stack):
        """Test that task execution and task roles are created"""
        template = assertions.Template.from_stack(production_ecs_stack)

        roles = template.find_resources('AWS::IAM::Role')

        # Should have at least execution role and task role
        assert len(roles) >= 2, 'Should have execution role and task role'

    def test_logging_enabled(self, production_ecs_stack):
        """Test that CloudWatch logging is enabled"""
        template = assertions.Template.from_stack(production_ecs_stack)

        # Should have log group
        template.has_resource_properties('AWS::Logs::LogGroup', {})

        # Task definition should reference log configuration
        task_defs = template.find_resources('AWS::ECS::TaskDefinition')
        task_def = list(task_defs.values())[0]
        container_defs = task_def['Properties']['ContainerDefinitions']

        log_config = container_defs[0].get('LogConfiguration')
        assert log_config is not None, 'Container should have log configuration'
        assert log_config['LogDriver'] == 'awslogs'

    def test_stack_outputs_exist(self, production_ecs_stack):
        """Test that stack exports necessary outputs"""
        template = assertions.Template.from_stack(production_ecs_stack)

        outputs = template.find_outputs('*')
        output_keys = set(outputs.keys())

        expected_outputs = {
            'LoadBalancerDNS',
            'EcrRepositoryUri',
            'ClusterName',
            'ServiceName',
        }

        for expected in expected_outputs:
            assert any(expected in key for key in output_keys), f'Should have output for {expected}'
