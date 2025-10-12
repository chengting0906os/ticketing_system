"""
Self-Hosted KVRocks Stack on ECS

Cost-effective alternative to AWS MemoryDB:
- KVRocks ECS Service: ~$96/month (vs MemoryDB ~$1,500/month)
- EFS for RocksDB persistence
- Service Discovery for application connection
- CloudWatch monitoring

Architecture:
- 2-3 Fargate tasks running KVRocks
- EFS volume mounted at /data for RocksDB
- Application connects via Service Discovery DNS
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_efs as efs,
    aws_logs as logs,
    aws_servicediscovery as servicediscovery,
)
from constructs import Construct


class KVRocksStack(Stack):
    """
    Self-hosted KVRocks service on ECS Fargate

    Benefits:
    - 15x cheaper than MemoryDB (~$96 vs ~$1,500/month)
    - Full control over KVRocks configuration
    - Persistent storage via EFS
    - Compatible with existing Lua scripts and Bitfield operations
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        app_security_group_id: str,
        environment: str = 'production',
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = environment

        # Import security group from VPC Stack by ID to avoid cyclic dependencies
        app_security_group = ec2.SecurityGroup.from_security_group_id(
            self, 'ImportedAppSecurityGroup', app_security_group_id
        )

        # ============= ECS Cluster =============

        # Create ECS cluster for both KVRocks and Application
        cluster = ecs.Cluster(
            self,
            'TicketingCluster',
            cluster_name=f'ticketing-cluster-{environment}',
            vpc=vpc,
            container_insights=True,
        )

        # Add Cloud Map namespace for Service Discovery
        cluster.add_default_cloud_map_namespace(
            name='ticketing.local',
            vpc=vpc,
        )

        # ============= Security Group for KVRocks =============

        kvrocks_security_group = ec2.SecurityGroup(
            self,
            'KVRocksSecurityGroup',
            vpc=vpc,
            description='Security group for KVRocks service',
            allow_all_outbound=True,
        )

        # Allow application to connect to KVRocks on port 6666
        kvrocks_security_group.add_ingress_rule(
            peer=app_security_group,
            connection=ec2.Port.tcp(6666),
            description='Allow application to connect to KVRocks',
        )

        # ============= EFS File System for RocksDB Data =============

        # Create EFS file system for persistent RocksDB storage
        file_system = efs.FileSystem(
            self,
            'KVRocksFileSystem',
            vpc=vpc,
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
        )

        # Allow KVRocks security group to access EFS
        file_system.connections.allow_from(
            kvrocks_security_group,
            ec2.Port.tcp(2049),
            'Allow KVRocks to access EFS',
        )

        # Create access point for KVRocks data
        access_point = file_system.add_access_point(
            'KVRocksAccessPoint',
            path='/kvrocks-data',
            create_acl=efs.Acl(
                owner_uid='1000',  # KVRocks user
                owner_gid='1000',
                permissions='755',
            ),
            posix_user=efs.PosixUser(
                uid='1000',
                gid='1000',
            ),
        )

        # ============= Task Definition =============

        # Resource allocation based on environment
        if environment == 'production':
            cpu = 512  # 0.5 vCPU
            memory = 1024  # 1 GB
            desired_count = 2  # Primary + standby
        else:  # development
            cpu = 256  # 0.25 vCPU
            memory = 512  # 0.5 GB
            desired_count = 1

        task_definition = ecs.FargateTaskDefinition(
            self,
            'KVRocksTaskDefinition',
            cpu=cpu,
            memory_limit_mib=memory,
            volumes=[
                ecs.Volume(
                    name='kvrocks-data',
                    efs_volume_configuration=ecs.EfsVolumeConfiguration(
                        file_system_id=file_system.file_system_id,
                        transit_encryption='ENABLED',
                        authorization_config=ecs.AuthorizationConfig(
                            access_point_id=access_point.access_point_id,
                        ),
                    ),
                )
            ],
        )

        # KVRocks container
        kvrocks_container = task_definition.add_container(
            'KVRocksContainer',
            image=ecs.ContainerImage.from_registry('apache/kvrocks:latest'),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix='kvrocks',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'KVROCKS_BIND': '0.0.0.0',
                'KVROCKS_PORT': '6666',
                'KVROCKS_DIR': '/data',
                'KVROCKS_WORKERS': '4',
                'KVROCKS_LOG_LEVEL': 'info' if environment == 'production' else 'debug',
            },
            command=[
                'kvrocks',
                '--bind',
                '0.0.0.0',
                '--port',
                '6666',
                '--dir',
                '/data',
                '--workers',
                '4',
            ],
            health_check=ecs.HealthCheck(
                command=['CMD-SHELL', 'redis-cli -p 6666 PING || exit 1'],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        # Mount EFS volume
        kvrocks_container.add_mount_points(
            ecs.MountPoint(
                container_path='/data',
                source_volume='kvrocks-data',
                read_only=False,
            )
        )

        # Expose port 6666
        kvrocks_container.add_port_mappings(
            ecs.PortMapping(
                container_port=6666,
                protocol=ecs.Protocol.TCP,
            )
        )

        # ============= ECS Service =============

        service = ecs.FargateService(
            self,
            'KVRocksService',
            cluster=cluster,
            task_definition=task_definition,
            desired_count=desired_count,
            service_name=f'kvrocks-{environment}',
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[kvrocks_security_group],
            enable_ecs_managed_tags=True,
            # Service discovery
            cloud_map_options=ecs.CloudMapOptions(
                name='kvrocks',
                dns_record_type=servicediscovery.DnsRecordType.A,
                dns_ttl=Duration.seconds(10),
            ),
            # Deployment configuration
            min_healthy_percent=50,  # Allow replacing one task at a time
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )

        # ============= CloudWatch Alarms =============

        # CPU alarm
        cloudwatch.Alarm(
            self,
            'KVRocksCPUAlarm',
            metric=service.metric_cpu_utilization(),
            threshold=80,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='KVRocks CPU > 80%',
        )

        # Memory alarm
        cloudwatch.Alarm(
            self,
            'KVRocksMemoryAlarm',
            metric=service.metric_memory_utilization(),
            threshold=85,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='KVRocks memory > 85%',
        )

        # ============= Outputs =============

        CfnOutput(
            self,
            'KVRocksServiceDiscoveryName',
            value='kvrocks.ticketing.local:6666',
            description='KVRocks connection endpoint (Service Discovery DNS)',
        )

        CfnOutput(
            self,
            'KVRocksEfsFileSystemId',
            value=file_system.file_system_id,
            description='EFS file system ID for KVRocks data',
        )

        CfnOutput(
            self,
            'KVRocksSecurityGroupId',
            value=kvrocks_security_group.security_group_id,
            description='Security group ID for KVRocks service',
        )

        # Store attributes for other stacks
        self.cluster = cluster  # ECS cluster for Application stack to use
        self.service = service
        self.kvrocks_security_group = kvrocks_security_group
        self.file_system = file_system
        self.connection_string = 'kvrocks.ticketing.local:6666'


# Cost estimation helper
def estimate_monthly_cost(environment: str) -> dict:
    """
    Estimate monthly cost for self-hosted KVRocks

    Returns cost breakdown in USD
    """
    if environment == 'production':
        # 2 tasks × 0.5 vCPU × $0.04/vCPU/hour × 730 hours
        fargate_cpu = 2 * 0.5 * 0.04 * 730  # $29.20
        # 2 tasks × 1GB × $0.004/GB/hour × 730 hours
        fargate_memory = 2 * 1 * 0.004 * 730  # $5.84
        # EFS: 100GB × $0.30/GB
        efs_storage = 100 * 0.30  # $30.00
        # EFS requests: ~1M requests/month × $0.01/1M
        efs_requests = 1 * 0.01  # $0.01

        total = fargate_cpu + fargate_memory + efs_storage + efs_requests

        return {
            'fargate_cpu': fargate_cpu,
            'fargate_memory': fargate_memory,
            'efs_storage': efs_storage,
            'efs_requests': efs_requests,
            'total': total,
            'vs_memorydb_savings': 1500 - total,  # MemoryDB costs ~$1500/month
        }
    else:  # development
        fargate_cpu = 1 * 0.25 * 0.04 * 730  # $7.30
        fargate_memory = 1 * 0.5 * 0.004 * 730  # $1.46
        efs_storage = 10 * 0.30  # $3.00
        efs_requests = 0.1 * 0.01  # $0.001

        total = fargate_cpu + fargate_memory + efs_storage + efs_requests

        return {
            'fargate_cpu': fargate_cpu,
            'fargate_memory': fargate_memory,
            'efs_storage': efs_storage,
            'efs_requests': efs_requests,
            'total': total,
        }
