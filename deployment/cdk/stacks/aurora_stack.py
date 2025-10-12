"""
Aurora Serverless v2 PostgreSQL Stack for High-Throughput Ticketing System

Optimized for 10,000 QPS with auto-scaling:
- Aurora Serverless v2 with 1 writer + 3 readers
- Auto-scaling: 8-128 ACU (16GB - 256GB RAM)
- RDS Proxy for connection pooling
- Perfect for ticketing: scales up during ticket sales, down during off-peak
- Enhanced monitoring and CloudWatch alarms
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_ec2 as ec2,
    aws_logs as logs,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class AuroraStack(Stack):
    """
    Aurora Serverless v2 cluster optimized for 10,000 QPS with auto-scaling

    Architecture:
    - 1 Writer: Serverless v2 (auto-scales 8-128 ACU)
    - 3 Readers: Serverless v2 (auto-scale with writer)
    - RDS Proxy: Connection pooling (up to 5000 connections)
    - Auto-scaling: Responds to actual load in real-time

    Cost benefits:
    - Pay only for actual usage (not fixed instance cost)
    - Scales down during off-peak hours
    - Scales up automatically during ticket sales
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        db_security_group_id: str,
        proxy_security_group_id: str,
        app_security_group_id: str,
        environment: str = 'production',
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = environment
        self.vpc = vpc

        # Import security groups from VPC Stack by ID to avoid cyclic dependencies
        self.db_security_group = ec2.SecurityGroup.from_security_group_id(
            self, 'ImportedDbSecurityGroup', db_security_group_id
        )
        self.proxy_security_group = ec2.SecurityGroup.from_security_group_id(
            self, 'ImportedProxySecurityGroup', proxy_security_group_id
        )
        self.app_security_group = ec2.SecurityGroup.from_security_group_id(
            self, 'ImportedAppSecurityGroup', app_security_group_id
        )

        # ============= Database Credentials =============

        db_credentials_secret = secretsmanager.Secret(
            self,
            'AuroraCredentials',
            secret_name=f'ticketing-aurora-{environment}',
            description='Aurora PostgreSQL credentials',
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "py_arch_lab"}',
                generate_string_key='password',
                exclude_punctuation=True,
                password_length=32,
            ),
        )

        # ============= Aurora Cluster Parameter Group =============

        # Optimized for high throughput
        cluster_parameter_group = rds.ParameterGroup(
            self,
            'ClusterParameterGroup',
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_4
            ),
            description='Optimized for 10K QPS',
            parameters={
                'max_connections': '5000',  # RDS Proxy will pool these
                'shared_buffers': '16384MB',  # 25% of RAM for writer (64GB * 0.25)
                'effective_cache_size': '48GB',  # 75% of RAM for writer
                'maintenance_work_mem': '2GB',
                'checkpoint_completion_target': '0.9',
                'wal_buffers': '16MB',
                'default_statistics_target': '100',
                'random_page_cost': '1.1',  # SSD optimization
                'effective_io_concurrency': '200',
                'work_mem': '32MB',
                'min_wal_size': '1GB',
                'max_wal_size': '4GB',
                'max_worker_processes': '8',
                'max_parallel_workers_per_gather': '4',
                'max_parallel_workers': '8',
                'max_parallel_maintenance_workers': '4',
            },
        )

        # ============= Aurora PostgreSQL Cluster =============

        # Serverless v2 scaling configuration based on environment
        if environment == 'production':
            # Production: High capacity for 10K QPS sustained
            # 1 ACU = 2GB RAM, ~1000 connections
            # 128 ACU = 256GB RAM, enough for peak 10K QPS
            min_acu = 8  # 16GB RAM minimum (low traffic periods)
            max_acu = 128  # 256GB RAM maximum (peak ticket sales)
            reader_count = 3  # 3 readers for read/write splitting
        else:  # development
            # Development: Lower capacity for testing
            min_acu = 0.5  # 1GB RAM minimum (cost-effective)
            max_acu = 16  # 32GB RAM maximum (development testing)
            reader_count = 1  # 1 reader for testing read/write splitting

        # Create Aurora Serverless v2 cluster
        aurora_cluster = rds.DatabaseCluster(
            self,
            'AuroraCluster',
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_4
            ),
            credentials=rds.Credentials.from_secret(db_credentials_secret),
            # Serverless v2 Writer
            writer=rds.ClusterInstance.serverless_v2(
                'Writer',
                publicly_accessible=False,
                enable_performance_insights=True,
                performance_insight_retention=rds.PerformanceInsightRetention.MONTHS_1,
            ),
            # Serverless v2 Readers (auto-scale with writer)
            readers=[
                rds.ClusterInstance.serverless_v2(
                    f'Reader{i}',
                    scale_with_writer=True,  # Match writer's scaling
                    publicly_accessible=False,
                    enable_performance_insights=True,
                    performance_insight_retention=rds.PerformanceInsightRetention.MONTHS_1,
                )
                for i in range(1, reader_count + 1)
            ],
            # Serverless v2 capacity range
            serverless_v2_min_capacity=min_acu,
            serverless_v2_max_capacity=max_acu,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[self.db_security_group],
            parameter_group=cluster_parameter_group,
            default_database_name='ticketing_system_db',
            # Storage configuration
            storage_encrypted=True,
            # Backup configuration
            backup=rds.BackupProps(
                retention=Duration.days(7 if environment == 'production' else 3),
                preferred_window='17:00-18:00',  # 1-2 AM Taiwan time (UTC+8)
            ),
            # Monitoring
            cloudwatch_logs_exports=['postgresql'],
            cloudwatch_logs_retention=logs.RetentionDays.ONE_MONTH,
            # Maintenance
            preferred_maintenance_window='sun:18:00-sun:19:00',  # 2-3 AM Taiwan time
            # Deletion protection
            deletion_protection=environment == 'production',
            removal_policy=(
                RemovalPolicy.SNAPSHOT if environment == 'production' else RemovalPolicy.DESTROY
            ),
        )

        # ============= RDS Proxy for Connection Pooling =============

        proxy = aurora_cluster.add_proxy(
            'AuroraProxy',
            secrets=[db_credentials_secret],
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.proxy_security_group],
            db_proxy_name=f'ticketing-proxy-{environment}',
            # Connection pool configuration
            max_connections_percent=90,  # Use up to 90% of max_connections
            max_idle_connections_percent=50,
            init_query='SELECT 1',  # Health check query
            # Session pinning filters (avoid pinning for better pooling)
            session_pinning_filters=[
                rds.SessionPinningFilter.EXCLUDE_VARIABLE_SETS,
            ],
            require_tls=True,
        )

        # ============= Security Group Rules (After Resources Created) =============
        # Configure security group rules after cluster and proxy are created
        # to avoid cyclic dependencies

        # Allow RDS Proxy to connect to Aurora database
        aurora_cluster.connections.allow_from(
            self.proxy_security_group,
            ec2.Port.tcp(5432),
            'Allow RDS Proxy to connect to Aurora',
        )

        # Allow application (ECS tasks) to connect to RDS Proxy
        proxy.connections.allow_from(
            self.app_security_group,
            ec2.Port.tcp(5432),
            'Allow application to connect to RDS Proxy',
        )

        # ============= CloudWatch Alarms =============

        # Writer CPU alarm
        cloudwatch.Alarm(
            self,
            'WriterHighCPU',
            metric=aurora_cluster.metric_cpu_utilization(
                dimensions_map={'DBClusterIdentifier': aurora_cluster.cluster_identifier}
            ),
            threshold=80,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='Writer CPU > 80% for 2 periods',
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Reader CPU alarm (for auto-scaling)
        cloudwatch.Alarm(
            self,
            'ReaderHighCPU',
            metric=cloudwatch.Metric(
                namespace='AWS/RDS',
                metric_name='CPUUtilization',
                dimensions_map={
                    'DBClusterIdentifier': aurora_cluster.cluster_identifier,
                    'Role': 'READER',
                },
                statistic='Average',
                period=Duration.minutes(5),
            ),
            threshold=70,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='Reader CPU > 70% - consider scaling',
        )

        # Database connections alarm
        cloudwatch.Alarm(
            self,
            'HighConnections',
            metric=aurora_cluster.metric_database_connections(),
            threshold=4000,  # 80% of max_connections (5000)
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='Database connections > 4000',
        )

        # ============= Outputs =============

        CfnOutput(
            self,
            'ClusterEndpoint',
            value=aurora_cluster.cluster_endpoint.hostname,
            description='Aurora cluster writer endpoint',
        )

        CfnOutput(
            self,
            'ReaderEndpoint',
            value=aurora_cluster.cluster_read_endpoint.hostname,
            description='Aurora cluster reader endpoint (load-balanced)',
        )

        CfnOutput(
            self,
            'ProxyEndpoint',
            value=proxy.endpoint,
            description='RDS Proxy endpoint for WRITE operations (recommended for INSERT/UPDATE/DELETE)',
        )

        CfnOutput(
            self,
            'AuroraReaderEndpoint',
            value=aurora_cluster.cluster_read_endpoint.hostname,
            description='Aurora reader endpoint for READ operations (SELECT) - load-balanced across read replicas',
        )

        CfnOutput(
            self,
            'SecretArn',
            value=db_credentials_secret.secret_arn,
            description='ARN of secret containing database credentials',
        )

        # Store attributes for other stacks
        self.aurora_cluster = aurora_cluster
        self.proxy = proxy
        self.db_credentials_secret = db_credentials_secret
        # Endpoints for read/write splitting
        self.proxy_endpoint = proxy.endpoint  # Writer endpoint (via RDS Proxy)
        self.reader_endpoint = aurora_cluster.cluster_read_endpoint.hostname  # Reader endpoint
