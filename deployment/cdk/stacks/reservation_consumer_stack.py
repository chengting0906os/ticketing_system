"""
Seat Reservation Consumer Stack
Deploys seat-reservation-consumer as an ECS Fargate background worker

Architecture:
- ECS Fargate task (1 vCPU + 2GB RAM)
- Auto-scaling 50-100 tasks (total: 50-100 vCPU)
- No ALB (background Kafka consumer + Kvrocks polling)
- Connects to Kvrocks and MSK (no Aurora needed)
"""

from aws_cdk import (
    CfnOutput,
    Stack,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_servicediscovery as servicediscovery,
)
from constructs import Construct


class ReservationConsumerStack(Stack):
    """
    Seat Reservation Consumer on ECS Fargate (Background Worker)

    Configuration:
    - 1 vCPU + 2GB RAM per task
    - 50-100 tasks with auto-scaling
    - Kafka consumer + Kvrocks polling for seat reservations
    - No database access needed (stateless)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        ecs_cluster: ecs.ICluster,
        aurora_cluster_secret: secretsmanager.ISecret,
        app_secrets: secretsmanager.ISecret,
        namespace: servicediscovery.IPrivateDnsNamespace,
        kafka_bootstrap_servers: str,
        kvrocks_endpoint: str,
        config: dict,
        **kwargs,
    ) -> None:
        """
        Initialize Seat Reservation Consumer Stack

        Args:
            vpc: VPC for ECS tasks
            ecs_cluster: Shared ECS cluster
            aurora_cluster_secret: Aurora credentials (for Settings model requirement)
            app_secrets: Shared JWT secrets from Aurora Stack
            namespace: Service Discovery namespace
            kvrocks_endpoint: Kvrocks endpoint (host:port)
            config: Environment configuration from config.yml
        """
        super().__init__(scope, construct_id, **kwargs)

        # Note: app_secrets is now passed from Aurora Stack (shared by all services)

        # Parse Kvrocks endpoint (format: "host:port")
        kvrocks_host, kvrocks_port = kvrocks_endpoint.split(':')

        # ============= ECR Repository =============
        consumer_repo = ecr.Repository.from_repository_name(
            self, 'ReservationConsumerRepo', repository_name='seat-reservation-consumer'
        )

        # ============= IAM Roles =============
        execution_role = iam.Role(
            self,
            'ExecutionRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    'service-role/AmazonECSTaskExecutionRolePolicy'
                ),
            ],
        )

        task_role = iam.Role(
            self,
            'TaskRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=['secretsmanager:GetSecretValue'],
                resources=['arn:aws:secretsmanager:*:*:secret:ticketing/*'],
            )
        )

        # ============= Task Definition =============
        task_def = ecs.FargateTaskDefinition(
            self,
            'TaskDef',
            memory_limit_mib=2048,  # 2GB RAM for consumer
            cpu=1024,  # 1 vCPU for consumer
            execution_role=execution_role,
            task_role=task_role,
        )

        # Main consumer container
        task_def.add_container(
            'Container',
            image=ecs.ContainerImage.from_ecr_repository(consumer_repo, tag='latest'),
            command=[
                'sh',
                '-c',
                'uv run python -m src.service.seat_reservation.driving_adapter.start_seat_reservation_consumer',
            ],
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='reservation-consumer', log_retention=logs.RetentionDays.ONE_WEEK
            ),
            environment={
                'SERVICE_TYPE': 'consumer',
                'SERVICE_NAME': 'seat-reservation-consumer',
                'LOG_LEVEL': config['log_level'],
                # No database needed for seat-reservation-consumer (stateless, uses Kvrocks only)
                # But Settings model requires POSTGRES_* env vars to be set
                'POSTGRES_SERVER': 'dummy',  # Not used, but required by Settings
                'POSTGRES_DB': 'dummy',
                'POSTGRES_PORT': '5432',
                # Kvrocks (EC2 instance) - Primary data store
                'KVROCKS_HOST': kvrocks_host,
                'KVROCKS_PORT': kvrocks_port,
                # Kafka (EC2-hosted cluster)
                'ENABLE_KAFKA': 'true',
                'KAFKA_BOOTSTRAP_SERVERS': kafka_bootstrap_servers,
                # JWT Authentication (required by Settings model, but not actually used)
                'ACCESS_TOKEN_EXPIRE_MINUTES': '30',
                'REFRESH_TOKEN_EXPIRE_DAYS': '7',
                # Event ID (for testing/development)
                'EVENT_ID': '1',
            },
            # Sensitive secrets injected from AWS Secrets Manager at runtime
            secrets={
                'SECRET_KEY': ecs.Secret.from_secrets_manager(app_secrets, 'SECRET_KEY'),
                'RESET_PASSWORD_TOKEN_SECRET': ecs.Secret.from_secrets_manager(
                    app_secrets, 'RESET_PASSWORD_TOKEN_SECRET'
                ),
                'VERIFICATION_TOKEN_SECRET': ecs.Secret.from_secrets_manager(
                    app_secrets, 'VERIFICATION_TOKEN_SECRET'
                ),
                'ALGORITHM': ecs.Secret.from_secrets_manager(app_secrets, 'ALGORITHM'),
                'POSTGRES_USER': ecs.Secret.from_secrets_manager(aurora_cluster_secret, 'username'),
                'POSTGRES_PASSWORD': ecs.Secret.from_secrets_manager(
                    aurora_cluster_secret, 'password'
                ),
            },
        )

        # ============= Service (No ALB for background worker) =============
        # Get environment from config (production or development)
        env_name = config.get('environment', 'production')
        service_name = f'ticketing-{env_name}-reservation-consumer-service'

        service = ecs.FargateService(
            self,
            'Service',
            service_name=service_name,
            cluster=ecs_cluster,
            task_definition=task_def,
            desired_count=config.get('consumers', {}).get('reservation', {}).get('min_tasks', 50),
            min_healthy_percent=50,  # Keep 50% running during deployment
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            enable_execute_command=True,  # Enable ECS Exec for debugging
            cloud_map_options=ecs.CloudMapOptions(
                name='seat-reservation-consumer',
                cloud_map_namespace=namespace,
                dns_record_type=servicediscovery.DnsRecordType.A,
            ),
        )

        # Auto-scaling: 50-100 tasks (50 vCPU - 100 vCPU)
        # Total resource usage at max: 100 vCPU + 200GB RAM
        scaling = service.auto_scale_task_count(
            min_capacity=config.get('consumers', {}).get('reservation', {}).get('min_tasks', 50),
            max_capacity=config.get('consumers', {}).get('reservation', {}).get('max_tasks', 100),
        )
        scaling.scale_on_cpu_utilization('CPUScaling', target_utilization_percent=70)
        scaling.scale_on_memory_utilization('MemoryScaling', target_utilization_percent=80)

        # ============= Outputs =============
        CfnOutput(
            self,
            'ServiceName',
            value=service.service_name,
            description='Seat reservation consumer service name',
        )

        self.service = service
