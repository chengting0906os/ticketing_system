"""
RDS PostgreSQL Stack - Single Instance (No Multi-AZ)

Architecture:
- 1 × Primary Instance (db.r6g.2xlarge - Graviton2 ARM)
- No standby replica (cost optimization for development)

Benefits: Lower costs, predictable performance, simpler capacity planning
"""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from constructs import Construct


class RdsPostgresStack(Stack):
    """
    RDS PostgreSQL Single Instance Stack

    Configuration from config.yml:
    - Instance: db.r6g.2xlarge (8 vCPU, 64 GB RAM, Graviton2 ARM)
    - Storage: gp3 with configurable size
    - Single instance (no Multi-AZ) for cost optimization

    Provisioned instance provides predictable performance and costs.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        config: dict,
        deploy_env: str = 'development',
        **kwargs,
    ) -> None:
        """
        Initialize RDS PostgreSQL Multi-AZ Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC to deploy RDS instance
            config: Environment configuration dictionary
            deploy_env: Deployment environment (development, staging, production)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.deploy_env = deploy_env

        # Extract RDS configuration
        rds_config = config.get('rds_postgres', {})
        instance_type_str = rds_config.get('instance_type', 'r6g.xlarge')
        storage_gb = rds_config.get('storage_gb', 100)
        max_storage_gb = rds_config.get('max_storage_gb', 500)

        # ============= Security Group =============
        self.db_security_group = ec2.SecurityGroup(
            self,
            'RdsSecurityGroup',
            vpc=vpc,
            description='Security group for RDS PostgreSQL',
            allow_all_outbound=False,
        )

        # Allow PostgreSQL port (5432) from within VPC
        self.db_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5432),
            description='PostgreSQL access from VPC',
        )

        # ============= Database Credentials =============
        db_credentials = rds.Credentials.from_generated_secret(
            username='ticketing_admin',
            secret_name=f'ticketing/{deploy_env}/rds-postgres/credentials',
        )

        # ============= Parameter Group =============
        # PostgreSQL 17 - minimal custom parameters (use RDS defaults for most)
        parameter_group = rds.ParameterGroup(
            self,
            'PostgresParameterGroup',
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_17),
            description='Optimized parameters for ticketing system',
            parameters={
                # Connection management
                'max_connections': '600',
                # Query planning for SSD
                'random_page_cost': '1.1',
                'effective_io_concurrency': '200',
                # Logging
                'log_statement': 'ddl',
                'log_min_duration_statement': '1000',
            },
        )

        # ============= RDS PostgreSQL Instance (Multi-AZ) =============
        self.instance = rds.DatabaseInstance(
            self,
            'PostgresInstance',
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_17),
            # Instance configuration
            instance_type=ec2.InstanceType(instance_type_str),
            instance_identifier=f'ticketing-{deploy_env}-postgres',
            # Single instance (no Multi-AZ) for cost optimization
            multi_az=False,
            # Database configuration
            database_name='ticketing_system_db',
            credentials=db_credentials,
            parameter_group=parameter_group,
            # Network configuration
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.db_security_group],
            # Storage configuration
            storage_type=rds.StorageType.GP3,
            allocated_storage=storage_gb,
            max_allocated_storage=max_storage_gb,  # Auto-scaling
            storage_encrypted=True,
            # Backup configuration
            backup_retention=Duration.days(7),
            preferred_backup_window='03:00-04:00',  # 3-4 AM UTC
            delete_automated_backups=False,
            # Monitoring
            enable_performance_insights=True,
            performance_insight_retention=rds.PerformanceInsightRetention.DEFAULT,
            cloudwatch_logs_exports=['postgresql', 'upgrade'],
            monitoring_interval=Duration.seconds(60),
            # Maintenance
            preferred_maintenance_window='sun:04:00-sun:05:00',
            auto_minor_version_upgrade=True,
            # Deletion protection
            deletion_protection=False,  # Set True for production
            removal_policy=RemovalPolicy.SNAPSHOT,
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'InstanceEndpoint',
            value=self.instance.db_instance_endpoint_address,
            description='RDS PostgreSQL endpoint',
            export_name=f'Ticketing{deploy_env.capitalize()}RdsEndpoint',
        )

        CfnOutput(
            self,
            'InstancePort',
            value=self.instance.db_instance_endpoint_port,
            description='RDS PostgreSQL port',
        )

        CfnOutput(
            self,
            'SecretArn',
            value=self.instance.secret.secret_arn if self.instance.secret else 'N/A',
            description='ARN of the secret containing database credentials',
            export_name=f'Ticketing{deploy_env.capitalize()}RdsSecretArn',
        )

        CfnOutput(
            self,
            'SecurityGroupId',
            value=self.db_security_group.security_group_id,
            description='Security group ID for database access',
        )

        # Store references
        self.vpc = vpc
        self.endpoint = self.instance.db_instance_endpoint_address
