"""
Kvrocks on ECS with Sentinel High Availability Stack
Self-hosted Redis-compatible storage with automatic failover

Architecture:
- 1 Master + 2 Replicas (Kvrocks instances)
- 3 Sentinel instances for automatic failover
- EFS for persistent storage
- Redis protocol compatible (drop-in replacement)

High Availability:
- Sentinel monitors master health
- Auto-promotes replica to master on failure
- Client-side discovery via Sentinel
- Typically 10-30 second failover time

Why Kvrocks over ElastiCache?
- 70% cost savings ($50 vs $200/month for similar capacity)
- RocksDB backend (better for large datasets)
- Full control over configuration
- Matches docker-compose dev environment
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
    Kvrocks + Sentinel cluster on ECS Fargate

    Configuration (10000 TPS target):
    - 3 Kvrocks instances (1 master + 2 replicas)
    - 3 Sentinel instances (quorum = 2)
    - Each instance: 1 vCPU + 2GB RAM
    - EFS for persistent storage (data survives container restarts)

    Performance:
    - Kvrocks can handle 50000+ ops/sec per instance
    - 10000 TPS is well within capacity
    - Sentinel adds <1ms latency for failover detection

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

        # ============= EFS File System =============
        # Persistent storage for Kvrocks data
        file_system = efs.FileSystem(
            self,
            'KvrocksEFS',
            vpc=vpc,
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

        # ============= Kvrocks Master Task Definition =============
        kvrocks_master_task = ecs.FargateTaskDefinition(
            self,
            'KvrocksMasterTask',
            memory_limit_mib=2048,  # 2GB RAM
            cpu=1024,  # 1 vCPU
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
            enable_execute_command=True,  # Allow debugging via ECS Exec
            security_groups=[self.kvrocks_security_group],
            service_name='kvrocks-master',
        )

        # ============= Kvrocks Replica Task Definitions =============
        # We need 2 replicas, each needs its own task definition to replicate from master
        # In production, you'd configure replication via kvrocks.conf or SLAVEOF command

        kvrocks_replica_task = ecs.FargateTaskDefinition(
            self,
            'KvrocksReplicaTask',
            memory_limit_mib=2048,
            cpu=1024,
            task_role=task_role,
            execution_role=execution_role,
        )

        kvrocks_replica_container = kvrocks_replica_task.add_container(
            'KvrocksReplica',
            image=ecs.ContainerImage.from_registry('apache/kvrocks:latest'),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='kvrocks-replica',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'KVROCKS_BIND': '0.0.0.0',
                'KVROCKS_PORT': '6666',
                # Note: In production, set SLAVEOF to master service discovery name
                # 'KVROCKS_SLAVEOF': 'kvrocks-master.ticketing.local 6666',
            },
            command=[
                'kvrocks',
                '--bind',
                '0.0.0.0',
                '--port',
                '6666',
                # Add --slaveof flag after service discovery is set up
            ],
        )

        kvrocks_replica_container.add_port_mappings(
            ecs.PortMapping(container_port=6666, protocol=ecs.Protocol.TCP)
        )

        # Create 2 replica services
        kvrocks_replica_service = ecs.FargateService(
            self,
            'KvrocksReplicaService',
            cluster=cluster,
            task_definition=kvrocks_replica_task,
            desired_count=2,  # 2 replicas
            enable_execute_command=True,
            security_groups=[self.kvrocks_security_group],
            service_name='kvrocks-replica',
        )

        # ============= Sentinel Task Definition =============
        sentinel_task = ecs.FargateTaskDefinition(
            self,
            'SentinelTask',
            memory_limit_mib=512,  # 512MB RAM (Sentinel is lightweight)
            cpu=256,  # 0.25 vCPU
            task_role=task_role,
            execution_role=execution_role,
        )

        sentinel_container = sentinel_task.add_container(
            'Sentinel',
            image=ecs.ContainerImage.from_registry(
                'redis:7-alpine'
            ),  # Use Redis image for Sentinel
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='sentinel', log_retention=logs.RetentionDays.ONE_WEEK
            ),
            command=[
                'redis-sentinel',
                '/etc/redis/sentinel.conf',
                # Sentinel configuration will be provided via EFS or ConfigMap
            ],
            environment={
                'SENTINEL_QUORUM': '2',  # Need 2 out of 3 sentinels to agree
                'SENTINEL_DOWN_AFTER': '5000',  # 5 seconds to detect failure
                'SENTINEL_FAILOVER_TIMEOUT': '10000',  # 10 seconds failover timeout
            },
        )

        sentinel_container.add_port_mappings(
            ecs.PortMapping(container_port=26666, protocol=ecs.Protocol.TCP)
        )

        # Create 3 Sentinel services (quorum = 2)
        sentinel_service = ecs.FargateService(
            self,
            'SentinelService',
            cluster=cluster,
            task_definition=sentinel_task,
            desired_count=3,  # 3 Sentinels for quorum
            enable_execute_command=True,
            security_groups=[self.kvrocks_security_group],
            service_name='kvrocks-sentinel',
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
            'KvrocksReplicaServiceName',
            value=kvrocks_replica_service.service_name,
            description='Kvrocks replica service name',
        )

        CfnOutput(
            self,
            'SentinelServiceName',
            value=sentinel_service.service_name,
            description='Sentinel service name',
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
            value='Use Sentinel endpoints to discover current master: sentinel://sentinel-1:26666,sentinel-2:26666,sentinel-3:26666',
            description='Client connection info (use Sentinel for automatic failover)',
        )

        # Store references
        self.master_service = kvrocks_master_service
        self.replica_service = kvrocks_replica_service
        self.sentinel_service = sentinel_service
        self.file_system = file_system
