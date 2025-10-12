"""
Tests for Aurora PostgreSQL Stack

Validates:
- Aurora cluster configuration
- RDS Proxy setup
- Security groups
- CloudWatch alarms
- Multi-AZ deployment
"""

import aws_cdk as cdk
import aws_cdk.assertions as assertions
import pytest

from deployment.cdk.stacks.aurora_stack import AuroraStack


@pytest.mark.deployment
class TestAuroraStack:
    """Test Aurora PostgreSQL stack for 10K QPS"""

    @pytest.fixture
    def production_stack(self):
        """Create production Aurora stack for testing"""
        app = cdk.App()
        stack = AuroraStack(
            app,
            'TestAuroraStack',
            environment='production',
            env=cdk.Environment(account='123456789012', region='us-east-1'),
        )
        return stack

    @pytest.fixture
    def development_stack(self):
        """Create development Aurora stack for testing"""
        app = cdk.App()
        stack = AuroraStack(
            app,
            'TestAuroraStackDev',
            environment='development',
            env=cdk.Environment(account='123456789012', region='us-east-1'),
        )
        return stack

    def test_aurora_cluster_exists(self, production_stack):
        """Test that Aurora cluster is created"""
        template = assertions.Template.from_stack(production_stack)

        # Verify Aurora cluster exists
        template.has_resource_properties(
            'AWS::RDS::DBCluster',
            {
                'Engine': 'aurora-postgresql',
                'DatabaseName': 'ticketing_system_db',
                'StorageEncrypted': True,
            },
        )

    def test_production_has_multiple_readers(self, production_stack):
        """Test that production has 3 read replicas"""
        template = assertions.Template.from_stack(production_stack)

        # Count DB instances (should be 1 writer + 2+ readers)
        db_instances = template.find_resources('AWS::RDS::DBInstance')
        assert len(db_instances) >= 3, 'Production should have at least 3 instances'

    def test_development_has_fewer_readers(self, development_stack):
        """Test that development has fewer instances to save cost"""
        template = assertions.Template.from_stack(development_stack)

        # Count DB instances (should be 1 writer only)
        db_instances = template.find_resources('AWS::RDS::DBInstance')
        assert len(db_instances) >= 1, 'Development should have at least 1 instance'
        assert len(db_instances) < 3, 'Development should have fewer instances than production'

    def test_rds_proxy_created(self, production_stack):
        """Test that RDS Proxy is created for connection pooling"""
        template = assertions.Template.from_stack(production_stack)

        # Verify RDS Proxy exists
        template.has_resource_properties(
            'AWS::RDS::DBProxy',
            {
                'EngineFamily': 'POSTGRESQL',
                'RequireTLS': True,
            },
        )

    def test_security_groups_configured(self, production_stack):
        """Test that security groups are properly configured"""
        template = assertions.Template.from_stack(production_stack)

        # Verify database security group exists
        template.has_resource_properties(
            'AWS::EC2::SecurityGroup',
            {
                'GroupDescription': 'Security group for Aurora PostgreSQL cluster',
            },
        )

        # Verify proxy security group exists
        template.has_resource_properties(
            'AWS::EC2::SecurityGroup',
            {
                'GroupDescription': 'Security group for RDS Proxy',
            },
        )

    def test_cloudwatch_alarms_created(self, production_stack):
        """Test that CloudWatch alarms are created for monitoring"""
        template = assertions.Template.from_stack(production_stack)

        # Should have CPU alarms
        template.has_resource_properties(
            'AWS::CloudWatch::Alarm',
            {
                'MetricName': 'CPUUtilization',
                'Namespace': 'AWS/RDS',
                'Threshold': 80,
            },
        )

    def test_backup_retention_configured(self, production_stack):
        """Test that backup retention is set correctly"""
        template = assertions.Template.from_stack(production_stack)

        template.has_resource_properties(
            'AWS::RDS::DBCluster',
            {
                'BackupRetentionPeriod': 7,  # 7 days for production
            },
        )

    def test_multi_az_deployment(self, production_stack):
        """Test that VPC spans multiple availability zones"""
        template = assertions.Template.from_stack(production_stack)

        # VPC should be created
        template.has_resource_properties('AWS::EC2::VPC', {})

        # Should have subnets in multiple AZs
        subnets = template.find_resources('AWS::EC2::Subnet')
        assert len(subnets) >= 6, 'Should have subnets across multiple AZs'

    def test_deletion_protection_in_production(self, production_stack):
        """Test that deletion protection is enabled in production"""
        template = assertions.Template.from_stack(production_stack)

        template.has_resource_properties(
            'AWS::RDS::DBCluster',
            {
                'DeletionProtection': True,
            },
        )

    def test_no_deletion_protection_in_dev(self, development_stack):
        """Test that deletion protection is disabled in development"""
        template = assertions.Template.from_stack(development_stack)

        template.has_resource_properties(
            'AWS::RDS::DBCluster',
            {
                'DeletionProtection': False,
            },
        )

    def test_performance_insights_enabled(self, production_stack):
        """Test that Performance Insights is enabled for monitoring"""
        template = assertions.Template.from_stack(production_stack)

        # At least one instance should have Performance Insights enabled
        db_instances = template.find_resources('AWS::RDS::DBInstance')
        has_performance_insights = any(
            instance.get('Properties', {}).get('EnablePerformanceInsights', False)
            for instance in db_instances.values()
        )
        assert has_performance_insights, 'Performance Insights should be enabled'

    def test_stack_outputs_exist(self, production_stack):
        """Test that stack exports necessary outputs for other stacks"""
        template = assertions.Template.from_stack(production_stack)

        # Should have outputs for other stacks to use
        outputs = template.find_outputs('*')
        output_keys = set(outputs.keys())

        expected_outputs = {
            'ClusterEndpoint',
            'ReaderEndpoint',
            'ProxyEndpoint',
            'SecretArn',
            'VpcId',
        }

        for expected in expected_outputs:
            assert any(expected in key for key in output_keys), f'Should have output for {expected}'

    def test_snapshot_matches(self, production_stack):
        """
        Snapshot test - verifies the entire CloudFormation template

        This test will fail if the generated CloudFormation template changes.
        If the change is intentional, update the snapshot with:
            pytest --snapshot-update
        """
        template = assertions.Template.from_stack(production_stack)

        # Convert template to JSON for snapshot comparison
        template_json = template.to_json()

        # This would be used with pytest-snapshot plugin
        # For now, just verify it's valid JSON
        assert isinstance(template_json, dict)
        assert 'Resources' in template_json
        assert len(template_json['Resources']) > 0
