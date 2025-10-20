"""
Ticketing Service Stack
Deploys ticketing-service on ECS Fargate with auto-scaling

Architecture:
- ECS Fargate task (8 vCPU + 16GB RAM + 16 workers)
- Auto-scaling 4-16 tasks based on CPU/memory
- ALB integration for HTTP traffic
- Service discovery via AWS Cloud Map
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    SecretValue,
    Stack,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_servicediscovery as servicediscovery,
)
from constructs import Construct


class TicketingServiceStack(Stack):
    """
    Ticketing Service on ECS Fargate

    Configuration:
    - 8 vCPU + 16GB RAM per task
    - 4-16 tasks with auto-scaling
    - Integrated with Aurora, Kvrocks, MSK
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        ecs_cluster: ecs.ICluster,
        alb_listener: elbv2.IApplicationListener,
        aurora_cluster_endpoint: str,
        aurora_cluster_secret: secretsmanager.ISecret,
        namespace: servicediscovery.IPrivateDnsNamespace,
        config: dict,
        **kwargs,
    ) -> None:
        """
        Initialize Ticketing Service Stack

        Args:
            vpc: VPC for ECS tasks
            ecs_cluster: Shared ECS cluster
            alb_listener: Shared ALB listener
            aurora_cluster_endpoint: Aurora endpoint
            aurora_cluster_secret: Aurora credentials
            namespace: Service Discovery namespace
            config: Environment configuration from config.yml
        """
        super().__init__(scope, construct_id, **kwargs)

        # ============= Secrets Manager =============
        app_secrets = secretsmanager.Secret(
            self,
            'AppSecrets',
            description='JWT secrets for Ticketing Service',
            secret_object_value={
                'SECRET_KEY': SecretValue.unsafe_plain_text(
                    'of8uBXD-S4KJKvu7-C4KVUSxQICl8fg5eMDXVtvBFPw'
                ),
                'RESET_PASSWORD_TOKEN_SECRET': SecretValue.unsafe_plain_text(
                    'FLcN0V9DQazw3YJI0yQOa84AkwPRQQlWt_3xYo0Rvv8'
                ),
                'VERIFICATION_TOKEN_SECRET': SecretValue.unsafe_plain_text(
                    'NowtYFO5QY5w1dYfVl4whZpCXB12MTBaq9L9OHu08XU'
                ),
                'ALGORITHM': SecretValue.unsafe_plain_text('HS256'),
            },
        )

        # ============= ECR Repository =============
        ticketing_repo = ecr.Repository.from_repository_name(
            self, 'TicketingRepo', repository_name='ticketing-service'
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
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=['xray:PutTraceSegments', 'xray:PutTelemetryRecords'],
                resources=['*'],
            )
        )

        # ============= Task Definition =============
        task_def = ecs.FargateTaskDefinition(
            self,
            'TaskDef',
            memory_limit_mib=config['ecs']['ticketing']['task_memory'],
            cpu=config['ecs']['ticketing']['task_cpu'],
            execution_role=execution_role,
            task_role=task_role,
        )

        # Main container
        container = task_def.add_container(
            'Container',
            image=ecs.ContainerImage.from_ecr_repository(ticketing_repo, tag='latest'),
            command=[
                'sh',
                '-c',
                'uv run granian src.service.ticketing.main:app --interface asgi --host 0.0.0.0 --port 8100 --workers ${WORKERS}',
            ],
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='ticketing', log_retention=logs.RetentionDays.ONE_WEEK
            ),
            environment={
                'SERVICE_NAME': 'ticketing-service',
                'LOG_LEVEL': config['log_level'],
                'WORKERS': str(config['ecs']['ticketing']['workers']),
                'OTEL_EXPORTER_OTLP_ENDPOINT': 'http://localhost:4317',
                'OTEL_EXPORTER_OTLP_PROTOCOL': 'grpc',
                'POSTGRES_SERVER': aurora_cluster_endpoint,
                'POSTGRES_DB': 'ticketing_system_db',
                'POSTGRES_PORT': '5432',
                'KVROCKS_HOST': 'kvrocks-master.ticketing.local',
                'KVROCKS_PORT': '6666',
                'ENABLE_KAFKA': 'false',
                'KAFKA_BOOTSTRAP_SERVERS': 'localhost:9092',
                'ACCESS_TOKEN_EXPIRE_MINUTES': '30',
                'REFRESH_TOKEN_EXPIRE_DAYS': '7',
            },
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
            health_check=ecs.HealthCheck(
                command=['CMD-SHELL', 'curl -f http://localhost:8100/health || exit 1'],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )
        container.add_port_mappings(ecs.PortMapping(container_port=8100))

        # ADOT sidecar
        adot = task_def.add_container(
            'ADOT',
            image=ecs.ContainerImage.from_registry(
                'public.ecr.aws/aws-observability/aws-otel-collector:latest'
            ),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='adot', log_retention=logs.RetentionDays.ONE_WEEK
            ),
            environment={
                'AWS_REGION': 'us-west-2',
                'AOT_CONFIG_CONTENT': """
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
processors:
  batch:
    timeout: 1s
    send_batch_size: 50
exporters:
  awsxray:
    region: us-west-2
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsxray]
""",
            },
            memory_reservation_mib=256,
        )
        adot.add_port_mappings(ecs.PortMapping(container_port=4317))

        # ============= Service =============
        service = ecs.FargateService(
            self,
            'Service',
            cluster=ecs_cluster,
            task_definition=task_def,
            desired_count=config['ecs']['min_tasks'],
            min_healthy_percent=0 if config['ecs']['min_tasks'] == 1 else 50,
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            cloud_map_options=ecs.CloudMapOptions(
                name='ticketing-service',
                cloud_map_namespace=namespace,
                dns_record_type=servicediscovery.DnsRecordType.A,
            ),
        )

        # Auto-scaling
        scaling = service.auto_scale_task_count(
            min_capacity=config['ecs']['min_tasks'], max_capacity=config['ecs']['max_tasks']
        )
        scaling.scale_on_cpu_utilization(
            'CPUScaling', target_utilization_percent=config['ecs']['cpu_threshold']
        )
        scaling.scale_on_memory_utilization(
            'MemoryScaling', target_utilization_percent=config['ecs']['memory_threshold']
        )

        # ALB Target Group
        alb_listener.add_targets(
            'TicketingTargets',
            port=8100,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[service],
            health_check=elbv2.HealthCheck(
                path='/health',
                interval=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=Duration.seconds(30),
            priority=10,
            conditions=[
                elbv2.ListenerCondition.path_patterns(
                    ['/api/user/*', '/api/event/*', '/api/booking/*']
                )
            ],
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'ServiceName',
            value=service.service_name,
            description='Ticketing service name',
        )

        self.service = service
