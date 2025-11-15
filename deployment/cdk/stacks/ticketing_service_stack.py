"""
Ticketing Service Stack (API Only)
Deploys ticketing API service on ECS Fargate

Architecture:
- ECS Fargate task (configurable vCPU + RAM + workers)
- Auto-scaling based on CPU/memory
- ALB integration for HTTP traffic (all /api/* routes)
- Service discovery via AWS Cloud Map
- Standalone architecture: Consumers run as separate ECS services
"""

from aws_cdk import (
    CfnOutput,
    Duration,
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
    Ticketing API Service on ECS Fargate (API Only)

    Configuration:
    - Configurable vCPU + RAM per task (from config.yml)
    - Auto-scaling based on CPU/memory thresholds
    - Handles all API endpoints: /api/user/*, /api/event/*, /api/booking/*, /api/reservation/*
    - Standalone architecture: Kafka consumers run as separate ECS services
    - Integrated with Aurora, Kvrocks (Kafka disabled for API service)
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
        app_secrets: secretsmanager.ISecret,
        namespace: servicediscovery.IPrivateDnsNamespace,
        kafka_bootstrap_servers: str,
        kvrocks_endpoint: str,
        kvrocks_security_group: ec2.ISecurityGroup,
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
            app_secrets: Shared JWT secrets from Aurora Stack
            namespace: Service Discovery namespace
            kafka_bootstrap_servers: Kafka endpoints
            kvrocks_endpoint: Kvrocks endpoint (host:port)
            kvrocks_security_group: Kvrocks EC2 security group
            config: Environment configuration from config.yml
        """
        super().__init__(scope, construct_id, **kwargs)

        # Note: app_secrets is now passed from Aurora Stack (shared by all services)

        # Parse Kvrocks endpoint (format: "host:port")
        kvrocks_host, kvrocks_port = kvrocks_endpoint.split(':')

        # ============= Security Group for ECS Service =============
        service_sg = ec2.SecurityGroup(
            self,
            'ServiceSecurityGroup',
            vpc=vpc,
            description='Security group for Ticketing API ECS service',
            allow_all_outbound=True,
        )

        # Allow ECS service to connect to Kvrocks
        service_sg.connections.allow_to(
            kvrocks_security_group,
            ec2.Port.tcp(int(kvrocks_port)),
            description='Allow connection to Kvrocks',
        )

        # ============= ECR Repository =============
        # Both services use the same image (they're the same codebase)
        api_repo = ecr.Repository.from_repository_name(
            self, 'APIRepo', repository_name='ticketing-service'
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
            memory_limit_mib=config['ecs']['api']['task_memory'],
            cpu=config['ecs']['api']['task_cpu'],
            execution_role=execution_role,
            task_role=task_role,
        )

        # Main API container (serves both ticketing and seat-reservation endpoints)
        container = task_def.add_container(
            'Container',
            image=ecs.ContainerImage.from_ecr_repository(api_repo, tag='latest'),
            command=[
                'sh',
                '-c',
                'uv run granian src.main:app --interface asgi --host 0.0.0.0 --port 8100 --workers ${WORKERS}',
            ],
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='api-service', log_retention=logs.RetentionDays.ONE_WEEK
            ),
            environment={
                'SERVICE_NAME': 'api-service',
                'DEBUG': str(config.get('debug', False)).lower(),
                'LOG_LEVEL': config['log_level'],
                'WORKERS': str(config['ecs']['api']['workers']),
                'OTEL_EXPORTER_OTLP_ENDPOINT': 'http://localhost:4317',
                'OTEL_EXPORTER_OTLP_PROTOCOL': 'grpc',
                'POSTGRES_SERVER': aurora_cluster_endpoint,
                'POSTGRES_DB': 'ticketing_system_db',
                'POSTGRES_PORT': '5432',
                'KVROCKS_HOST': kvrocks_host,
                'KVROCKS_PORT': kvrocks_port,
                'ENABLE_KAFKA': 'false',
                'KAFKA_BOOTSTRAP_SERVERS': kafka_bootstrap_servers,
                'DEPLOY_ENV': config.get('environment', 'development'),
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

        # ADOT sidecar for OpenTelemetry
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
        # Get environment from config (production or development)
        env_name = config.get('environment', 'development')
        service_name = f'ticketing-{env_name}-ticketing-service'

        service = ecs.FargateService(
            self,
            'Service',
            service_name=service_name,
            cluster=ecs_cluster,
            task_definition=task_def,
            desired_count=config['ecs']['min_tasks'],
            min_healthy_percent=0 if config['ecs']['min_tasks'] == 1 else 50,
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            enable_execute_command=True,  # Enable ECS Exec for debugging
            security_groups=[service_sg],  # Explicit security group for network access
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

        # ALB Target Group - Handle all /api/* routes
        alb_listener.add_targets(
            'APITargets',
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
                elbv2.ListenerCondition.path_patterns(['/api/*'])  # All API routes
            ],
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'ServiceName',
            value=service.service_name,
            description='API service name',
        )

        self.service = service
