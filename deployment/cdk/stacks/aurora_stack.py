"""
Aurora Serverless v2 Stack for Ticketing System
Provides highly available PostgreSQL with 1 writer + 1 reader for read-write splitting

Architecture:
- Aurora Serverless v2 cluster (auto-scaling 2-64 ACU for 10000 TPS)
- 1 Writer instance (primary, handles all writes)
- 1 Reader instance (read replica, offloads SELECT queries)
- Automatic failover in seconds
- Continuous backup to S3
"""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, aws_ec2 as ec2, aws_rds as rds
from constructs import Construct


class AuroraStack(Stack):
    """
    Aurora Serverless v2 PostgreSQL cluster with read-write splitting

    Configuration:
    - Engine: PostgreSQL 16 (compatible with existing codebase)
    - Scaling: 2-64 ACU (optimized for 10000 TPS workload)
    - Instances: 1 writer + 1 reader for high availability
    - Backup: 7-day retention with point-in-time recovery
    - Security: VPC isolated, encrypted at rest and in transit

    Performance (10000 TPS target):
    - 2 ACU minimum: ~500 TPS (idle state, saves cost)
    - 64 ACU maximum: ~15000+ TPS (peak capacity)
    - Auto-scales based on CPU/connections

    See also: DATABASE_SPEC.md for connection pooling and query optimization
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        **kwargs,
    ) -> None:
        """
        Initialize Aurora Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC to deploy Aurora cluster (shared with ECS and other services)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # ============= Security Group =============
        # Allow PostgreSQL traffic from application services
        self.db_security_group = ec2.SecurityGroup(
            self,
            'AuroraSecurityGroup',
            vpc=vpc,
            description='Security group for Aurora PostgreSQL cluster',
            allow_all_outbound=False,  # Database should not initiate outbound connections
        )

        # Allow PostgreSQL port (5432) from within VPC
        self.db_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5432),
            description='PostgreSQL access from VPC',
        )

        # ============= Database Credentials =============
        # Auto-generate secure password and store in Secrets Manager
        db_credentials = rds.Credentials.from_generated_secret(
            username='ticketing_admin',
            secret_name='ticketing/aurora/credentials',
        )

        # ============= Aurora Serverless v2 Cluster =============
        # Configured for 10000 TPS workload
        # 2 ACU min (idle) → 64 ACU max (peak load)
        # Estimated cost: ~$500/month (idle) to ~$15,000/month (sustained peak)

        self.cluster = rds.DatabaseCluster(
            self,
            'AuroraCluster',
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_6  # PostgreSQL 16.6
            ),
            # Serverless v2 scaling configuration for 10000 TPS
            serverless_v2_min_capacity=2,  # Minimum: 2 ACU (~4 GB RAM, ~$0.24/hour)
            serverless_v2_max_capacity=64,  # Maximum: 64 ACU (~128 GB RAM, ~$15.36/hour)
            # Cluster configuration
            cluster_identifier='ticketing-aurora-cluster',
            default_database_name='ticketing_system_db',
            credentials=db_credentials,
            # Writer instance (primary)
            writer=rds.ClusterInstance.serverless_v2(
                'Writer',
                enable_performance_insights=True,
                performance_insight_retention=rds.PerformanceInsightRetention.DEFAULT,
            ),
            # Reader instances (read replicas)
            readers=[
                rds.ClusterInstance.serverless_v2(
                    'Reader1',
                    scale_with_writer=True,  # Match writer's capacity for consistent performance
                    enable_performance_insights=True,
                )
            ],
            # Network configuration
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS  # Private subnets with NAT
            ),
            security_groups=[self.db_security_group],
            # Backup configuration
            backup=rds.BackupProps(
                retention=Duration.days(7),  # 7-day backup retention
                preferred_window='03:00-04:00',  # Backup at 3-4 AM UTC (11 AM-12 PM Taipei)
            ),
            # Storage configuration
            storage_encrypted=True,  # Encrypt data at rest
            storage_type=rds.DBClusterStorageType.AURORA,  # Aurora storage (auto-scaling)
            # Monitoring
            cloudwatch_logs_exports=['postgresql'],  # Export logs to CloudWatch
            monitoring_interval=Duration.seconds(60),  # Enhanced monitoring every 60s
            # Maintenance
            preferred_maintenance_window='sun:04:00-sun:05:00',  # Sunday 4-5 AM UTC
            # Deletion protection
            deletion_protection=True,  # Prevent accidental deletion
            removal_policy=RemovalPolicy.SNAPSHOT,  # Create snapshot on stack deletion
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'ClusterEndpoint',
            value=self.cluster.cluster_endpoint.hostname,
            description='Aurora cluster writer endpoint (for writes)',
            export_name='TicketingAuroraWriterEndpoint',
        )

        CfnOutput(
            self,
            'ReaderEndpoint',
            value=self.cluster.cluster_read_endpoint.hostname,
            description='Aurora cluster reader endpoint (for reads)',
            export_name='TicketingAuroraReaderEndpoint',
        )

        CfnOutput(
            self,
            'ClusterPort',
            value=str(self.cluster.cluster_endpoint.port),
            description='Aurora cluster port (default: 5432)',
        )

        CfnOutput(
            self,
            'SecretArn',
            value=self.cluster.secret.secret_arn if self.cluster.secret else 'N/A',
            description='ARN of the secret containing database credentials',
            export_name='TicketingAuroraSecretArn',
        )

        CfnOutput(
            self,
            'SecurityGroupId',
            value=self.db_security_group.security_group_id,
            description='Security group ID for database access',
            export_name='TicketingAuroraSecurityGroupId',
        )

        # Store references for other stacks
        self.vpc = vpc
