"""
Simplified Kvrocks on ECS Stack
Self-hosted Redis-compatible storage (single master configuration)

Architecture:
- 1 Master only (no replicas, no sentinels)
- EFS for persistent storage
- Redis protocol compatible (drop-in replacement)

Performance (10000 TPS target):
- Kvrocks can handle 50000+ ops/sec per instance
- 10000 TPS is well within capacity
- Single instance is sufficient for testing/development

Why Kvrocks over ElastiCache?
- 90% cost savings ($24 vs $200/month)
- RocksDB backend (better for large datasets)
- Full control over configuration
- Matches docker-compose dev environment

Note: This is a simplified setup without HA for performance testing.
"""

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_efs as efs,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class KvrocksStack(Stack):
    """
    Simplified Kvrocks on ECS Fargate (Single Master)

    Configuration (10000 TPS target):
    - 1 Kvrocks master instance
    - 4 vCPU + 8GB RAM (handles 50,000+ ops/sec)
    - EFS for persistent storage (data survives container restarts)

    Performance:
    - Kvrocks can handle 50000+ ops/sec per instance
    - 10000 TPS is well within capacity

    See also: KVROCKS_SPEC.md for client configuration
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        cluster: ecs.ICluster,
        **kwargs,
    ) -> None:
        """
        Initialize Kvrocks Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC for Kvrocks deployment
            cluster: ECS cluster to deploy Kvrocks tasks
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # ============= Security Group =============
        self.kvrocks_security_group = ec2.SecurityGroup(
            self,
            'KvrocksSecurityGroup',
            vpc=vpc,
            description='Security group for Kvrocks cluster',
            allow_all_outbound=True,  # Allow Kvrocks replication and Sentinel communication
        )

        # Allow Redis protocol port (6666) from within VPC
        self.kvrocks_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(6666),
            description='Kvrocks Redis protocol port',
        )

        # Allow Sentinel port (26666) for sentinel-to-sentinel communication
        self.kvrocks_security_group.add_ingress_rule(
            peer=self.kvrocks_security_group,
            connection=ec2.Port.tcp(26666),
            description='Sentinel communication port',
        )

        # ============= EFS Security Group =============
        # Security group for EFS mount targets
        efs_security_group = ec2.SecurityGroup(
            self,
            'EFSSecurityGroup',
            vpc=vpc,
            description='Security group for EFS mount targets',
            allow_all_outbound=False,
        )

        # Allow NFS traffic from Kvrocks containers
        efs_security_group.add_ingress_rule(
            peer=self.kvrocks_security_group,
            connection=ec2.Port.tcp(2049),
            description='NFS access from Kvrocks containers',
        )

        # ============= EFS File System =============
        # Persistent storage for Kvrocks data
        file_system = efs.FileSystem(
            self,
            'KvrocksEFS',
            vpc=vpc,
            security_group=efs_security_group,
            encrypted=True,
            lifecycle_policy=efs.LifecyclePolicy.AFTER_14_DAYS,  # Move to IA after 14 days
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
            removal_policy=RemovalPolicy.RETAIN,  # Keep data on stack deletion
        )

        # Access point for Kvrocks data
        access_point = file_system.add_access_point(
            'KvrocksAccessPoint',
            path='/kvrocks-data',
            create_acl=efs.Acl(owner_uid='999', owner_gid='999', permissions='755'),
            posix_user=efs.PosixUser(uid='999', gid='999'),
        )

        # ============= Task Role =============
        task_role = iam.Role(
            self,
            'KvrocksTaskRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
        )

        # Grant EFS mount permissions to task role (needed for EFS IAM auth)
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    'elasticfilesystem:ClientMount',
                    'elasticfilesystem:ClientWrite',
                    'elasticfilesystem:ClientRootAccess',
                ],
                resources=[file_system.file_system_arn],
                conditions={
                    'StringEquals': {
                        'elasticfilesystem:AccessPointArn': access_point.access_point_arn
                    }
                },
            )
        )

        # ============= Task Execution Role =============
        execution_role = iam.Role(
            self,
            'KvrocksExecutionRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    'service-role/AmazonECSTaskExecutionRolePolicy'
                )
            ],
        )

        # Grant EFS mount permissions to execution role
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    'elasticfilesystem:ClientMount',
                    'elasticfilesystem:ClientWrite',
                    'elasticfilesystem:ClientRootAccess',
                ],
                resources=[file_system.file_system_arn],
                conditions={
                    'StringEquals': {
                        'elasticfilesystem:AccessPointArn': access_point.access_point_arn
                    }
                },
            )
        )

        # Note: EFS File System Policy would be ideal but CDK doesn't provide a construct
        # The IAM permissions on Task Role + Execution Role should be sufficient

        # ============= Kvrocks Master Task Definition =============
        kvrocks_master_task = ecs.FargateTaskDefinition(
            self,
            'KvrocksMasterTask',
            memory_limit_mib=8192,  # 8GB RAM (sufficient for high-throughput caching)
            cpu=4096,  # 4 vCPU (handles 10000+ TPS easily)
            task_role=task_role,
            execution_role=execution_role,
            volumes=[
                ecs.Volume(
                    name='kvrocks-data',
                    efs_volume_configuration=ecs.EfsVolumeConfiguration(
                        file_system_id=file_system.file_system_id,
                        transit_encryption='ENABLED',
                        authorization_config=ecs.AuthorizationConfig(
                            access_point_id=access_point.access_point_id, iam='ENABLED'
                        ),
                    ),
                )
            ],
        )

        kvrocks_master_container = kvrocks_master_task.add_container(
            'KvrocksMaster',
            image=ecs.ContainerImage.from_registry('apache/kvrocks:latest'),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='kvrocks-master',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'KVROCKS_BIND': '0.0.0.0',
                'KVROCKS_PORT': '6666',
                'KVROCKS_DIR': '/var/lib/kvrocks/data',
                'KVROCKS_MAXCLIENTS': '10000',
                'KVROCKS_TIMEOUT': '300',
            },
            command=[
                'kvrocks',
                '--bind',
                '0.0.0.0',
                '--port',
                '6666',
                '--dir',
                '/var/lib/kvrocks/data',
            ],
        )

        kvrocks_master_container.add_port_mappings(
            ecs.PortMapping(container_port=6666, protocol=ecs.Protocol.TCP)
        )

        kvrocks_master_container.add_mount_points(
            ecs.MountPoint(
                container_path='/var/lib/kvrocks/data',
                source_volume='kvrocks-data',
                read_only=False,
            )
        )

        # Create Kvrocks master service
        kvrocks_master_service = ecs.FargateService(
            self,
            'KvrocksMasterService',
            cluster=cluster,
            task_definition=kvrocks_master_task,
            desired_count=1,  # Only 1 master
            min_healthy_percent=70,  # Keep 70% healthy during deployments
            max_healthy_percent=200,  # Allow double capacity during rollout
            enable_execute_command=True,  # Allow debugging via ECS Exec
            security_groups=[self.kvrocks_security_group],
            service_name='kvrocks-master',
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'KvrocksMasterServiceName',
            value=kvrocks_master_service.service_name,
            description='Kvrocks master service name',
        )

        CfnOutput(
            self,
            'EFSFileSystemId',
            value=file_system.file_system_id,
            description='EFS file system ID for Kvrocks data',
        )

        CfnOutput(
            self,
            'ConnectionInfo',
            value='Direct connection to master: kvrocks-master.ticketing.local:6666',
            description='Client connection info (single master, no sentinel)',
        )

        # Store references
        self.master_service = kvrocks_master_service
        self.file_system = file_system
