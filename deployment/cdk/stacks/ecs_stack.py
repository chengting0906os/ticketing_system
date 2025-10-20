"""
ECS Fargate Stack for Ticketing System Microservices
Deploys ticketing-service and seat-reservation-service on serverless containers

Architecture:
- ECS Fargate (serverless containers, no EC2 management)
- Application Load Balancer for traffic distribution
- Auto-scaling based on CPU/memory utilization
- Service discovery via AWS Cloud Map
- Integration with Aurora, MSK, and Kvrocks

Performance (10000 TPS target):
- Ticketing Service: 4-16 tasks (auto-scaling)
  - Each task: 8 vCPU + 16GB RAM + 16 workers
  - Total capacity: 32-128 vCPU, 64-256GB RAM
- Seat Reservation Service: 4-16 tasks (auto-scaling)
  - Each task: 2 vCPU + 4GB RAM
  - Total capacity: 8-32 vCPU, 16-64GB RAM
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


class ECSStack(Stack):
    """
    ECS Fargate stack for microservices deployment

    Services:
    - ticketing-service: Handles user operations (booking, payments)
    - seat-reservation-service: Manages seat inventory and reservations

    Configuration for 10000 TPS:
    - Min tasks: 4 per service (always-on capacity)
    - Max tasks: 16 per service (burst capacity)
    - Auto-scaling triggers: CPU > 70% or Memory > 80%
    - Health checks: HTTP /health endpoint every 30s

    See also: TICKETING_SERVICE_SPEC.md, SEAT_RESERVATION_SPEC.md
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        aurora_cluster_endpoint: str,
        aurora_cluster_secret: secretsmanager.ISecret,
        aurora_security_group: ec2.ISecurityGroup,
        kvrocks_security_group: ec2.ISecurityGroup,
        namespace: servicediscovery.IPrivateDnsNamespace,
        **kwargs,
    ) -> None:
        """
        Initialize ECS Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC for ECS tasks
            aurora_cluster_endpoint: Aurora cluster endpoint for database connection
            aurora_cluster_secret: Aurora secret containing auto-generated credentials
            aurora_security_group: Aurora security group (for database access)
            kvrocks_security_group: Kvrocks security group (for cache access)
            namespace: Service Discovery namespace (from Aurora Stack)
            **kwargs: Additional stack properties

        Note: MSK security group removed - MSK Serverless manages its own security
        """
        super().__init__(scope, construct_id, **kwargs)

        # ============= Secrets Manager =============
        # Create a single secret containing all sensitive application secrets (JWT keys only)
        # Database password comes from Aurora's auto-generated secret
        app_secrets = secretsmanager.Secret(
            self,
            'AppSecrets',
            description='Sensitive configuration for Ticketing System (JWT keys)',
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

        # ============= ECS Cluster =============
        cluster = ecs.Cluster(
            self,
            'TicketingCluster',
            cluster_name='ticketing-cluster',
            vpc=vpc,
            container_insights=True,  # Enable CloudWatch Container Insights
        )

        # ============= Application Load Balancer =============
        alb = elbv2.ApplicationLoadBalancer(
            self,
            'TicketingALB',
            vpc=vpc,
            internet_facing=True,  # Public-facing ALB
            load_balancer_name='ticketing-alb',
        )

        # ALB listener (HTTP - in production, add HTTPS with ACM certificate)
        listener = alb.add_listener(
            'HttpListener',
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=404,
                content_type='application/json',
                message_body='{"error": "Not Found"}',
            ),
        )

        # ============= Service Discovery Namespace =============
        # Note: namespace is now passed from Aurora Stack (created there for all stacks to use)

        # ============= ECR Repositories (Import Existing) =============
        # Import pre-existing ECR repositories (created by deploy-all.sh or manually)
        # Use from_repository_name to reference existing repos instead of creating new ones
        ticketing_repo = ecr.Repository.from_repository_name(
            self,
            'TicketingServiceRepo',
            repository_name='ticketing-service',
        )

        reservation_repo = ecr.Repository.from_repository_name(
            self,
            'ReservationServiceRepo',
            repository_name='seat-reservation-service',
        )

        # ============= Task Execution Role =============
        # IAM role for ECS tasks to pull images and write logs
        execution_role = iam.Role(
            self,
            'ECSTaskExecutionRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    'service-role/AmazonECSTaskExecutionRolePolicy'
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    'AmazonEC2ContainerRegistryReadOnly'
                ),
            ],
        )

        # ============= Task Role =============
        # IAM role for application to access AWS services (Secrets Manager, etc.)
        task_role = iam.Role(
            self,
            'ECSTaskRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
        )

        # Grant access to Secrets Manager for database credentials
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=['secretsmanager:GetSecretValue'],
                resources=['arn:aws:secretsmanager:*:*:secret:ticketing/*'],
            )
        )

        # Grant access to X-Ray for ADOT Collector to send traces
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    'xray:PutTraceSegments',
                    'xray:PutTelemetryRecords',
                ],
                resources=['*'],
            )
        )

        # ============= Ticketing Service =============
        ticketing_task_def = ecs.FargateTaskDefinition(
            self,
            'TicketingTaskDef',
            memory_limit_mib=16384,  # 16GB RAM (8 vCPU requires min 16GB)
            cpu=8192,  # 8 vCPU (2x worker count for I/O-bound workload)
            execution_role=execution_role,
            task_role=task_role,
        )

        ticketing_container = ticketing_task_def.add_container(
            'TicketingContainer',
            image=ecs.ContainerImage.from_ecr_repository(ticketing_repo, tag='latest'),
            command=[
                'sh',
                '-c',
                'uv run granian src.service.ticketing.main:app --interface asgi --host 0.0.0.0 --port 8100 --workers ${WORKERS}',
            ],
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='ticketing',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'SERVICE_NAME': 'ticketing-service',
                'LOG_LEVEL': 'INFO',
                'WORKERS': '16',  # 16 workers for 8 vCPU (2x CPU, balanced for I/O + CPU)
                # OpenTelemetry - Send to ADOT Collector sidecar (localhost:4317)
                'OTEL_EXPORTER_OTLP_ENDPOINT': 'http://localhost:4317',
                'OTEL_EXPORTER_OTLP_PROTOCOL': 'grpc',
                # Database (Aurora PostgreSQL)
                'POSTGRES_SERVER': aurora_cluster_endpoint,
                'POSTGRES_DB': 'ticketing_system_db',  # Match Aurora default_database_name
                'POSTGRES_PORT': '5432',
                # Kvrocks (Service Discovery DNS)
                'KVROCKS_HOST': 'kvrocks-master.ticketing.local',
                'KVROCKS_PORT': '6666',
                # Kafka MSK (disabled until MSK deployed)
                'ENABLE_KAFKA': 'false',  # Set to 'true' after MSK is ready
                'KAFKA_BOOTSTRAP_SERVERS': 'localhost:9092',  # TODO: Update with MSK endpoints
                # JWT Authentication - Non-sensitive configuration
                'ACCESS_TOKEN_EXPIRE_MINUTES': '30',
                'REFRESH_TOKEN_EXPIRE_DAYS': '7',
            },
            # Sensitive secrets injected from AWS Secrets Manager at runtime
            secrets={
                # JWT keys from application secrets
                'SECRET_KEY': ecs.Secret.from_secrets_manager(app_secrets, 'SECRET_KEY'),
                'RESET_PASSWORD_TOKEN_SECRET': ecs.Secret.from_secrets_manager(
                    app_secrets, 'RESET_PASSWORD_TOKEN_SECRET'
                ),
                'VERIFICATION_TOKEN_SECRET': ecs.Secret.from_secrets_manager(
                    app_secrets, 'VERIFICATION_TOKEN_SECRET'
                ),
                'ALGORITHM': ecs.Secret.from_secrets_manager(app_secrets, 'ALGORITHM'),
                # Database credentials from Aurora auto-generated secret
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

        ticketing_container.add_port_mappings(
            ecs.PortMapping(container_port=8100, protocol=ecs.Protocol.TCP)
        )

        # Add ADOT Collector sidecar to forward traces to X-Ray
        adot_container = ticketing_task_def.add_container(
            'ADOTCollector',
            image=ecs.ContainerImage.from_registry(
                'public.ecr.aws/aws-observability/aws-otel-collector:latest'
            ),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='adot-collector',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'AWS_REGION': 'us-west-2',  # Set region for ADOT Collector
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
            memory_reservation_mib=256,  # Reserve 256MB for ADOT
        )

        adot_container.add_port_mappings(
            ecs.PortMapping(container_port=4317, protocol=ecs.Protocol.TCP)
        )

        # Create Fargate service for ticketing
        ticketing_service = ecs.FargateService(
            self,
            'TicketingService',
            cluster=cluster,
            task_definition=ticketing_task_def,
            desired_count=4,  # Start with 4 tasks for 10000 TPS
            min_healthy_percent=50,  # Allow 50% capacity during deployments
            max_healthy_percent=200,  # Double capacity during rollout
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            cloud_map_options=ecs.CloudMapOptions(
                name='ticketing-service',
                cloud_map_namespace=namespace,
                dns_record_type=servicediscovery.DnsRecordType.A,
            ),
        )

        # Security groups for Aurora, MSK, Kvrocks already allow VPC traffic
        # No need to modify them here (prevents cyclic dependencies)

        # Auto-scaling for ticketing service
        ticketing_scaling = ticketing_service.auto_scale_task_count(
            min_capacity=4,
            max_capacity=16,  # 4-16 tasks for 10000 TPS
        )
        ticketing_scaling.scale_on_cpu_utilization(
            'TicketingCPUScaling', target_utilization_percent=70
        )
        ticketing_scaling.scale_on_memory_utilization(
            'TicketingMemoryScaling', target_utilization_percent=80
        )

        # Add ticketing service to ALB
        listener.add_targets(
            'TicketingTargets',
            port=8100,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[ticketing_service],
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

        # ============= Seat Reservation Service =============
        reservation_task_def = ecs.FargateTaskDefinition(
            self,
            'ReservationTaskDef',
            memory_limit_mib=4096,  # 4GB RAM
            cpu=2048,  # 2 vCPU
            execution_role=execution_role,
            task_role=task_role,
        )

        reservation_container = reservation_task_def.add_container(
            'ReservationContainer',
            image=ecs.ContainerImage.from_ecr_repository(reservation_repo, tag='latest'),
            command=[
                'sh',
                '-c',
                'uv run granian src.service.seat_reservation.main:app --interface asgi --host 0.0.0.0 --port 8200 --workers 4',
            ],
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='reservation',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'SERVICE_NAME': 'seat-reservation-service',
                'LOG_LEVEL': 'INFO',
                # OpenTelemetry - Send to ADOT Collector sidecar (localhost:4317)
                'OTEL_EXPORTER_OTLP_ENDPOINT': 'http://localhost:4317',
                'OTEL_EXPORTER_OTLP_PROTOCOL': 'grpc',
                # Database (Aurora PostgreSQL)
                'POSTGRES_SERVER': aurora_cluster_endpoint,
                'POSTGRES_DB': 'ticketing_system_db',  # Match Aurora default_database_name
                'POSTGRES_PORT': '5432',
                # Kvrocks (Service Discovery DNS)
                'KVROCKS_HOST': 'kvrocks-master.ticketing.local',
                'KVROCKS_PORT': '6666',
                # Kafka MSK (disabled until MSK deployed)
                'ENABLE_KAFKA': 'false',  # Set to 'true' after MSK is ready
                'KAFKA_BOOTSTRAP_SERVERS': 'localhost:9092',  # TODO: Update with MSK endpoints
                # JWT Authentication - Non-sensitive configuration
                'ACCESS_TOKEN_EXPIRE_MINUTES': '30',
                'REFRESH_TOKEN_EXPIRE_DAYS': '7',
            },
            # Sensitive secrets injected from AWS Secrets Manager at runtime
            secrets={
                # JWT keys from application secrets
                'SECRET_KEY': ecs.Secret.from_secrets_manager(app_secrets, 'SECRET_KEY'),
                'RESET_PASSWORD_TOKEN_SECRET': ecs.Secret.from_secrets_manager(
                    app_secrets, 'RESET_PASSWORD_TOKEN_SECRET'
                ),
                'VERIFICATION_TOKEN_SECRET': ecs.Secret.from_secrets_manager(
                    app_secrets, 'VERIFICATION_TOKEN_SECRET'
                ),
                'ALGORITHM': ecs.Secret.from_secrets_manager(app_secrets, 'ALGORITHM'),
                # Database credentials from Aurora auto-generated secret
                'POSTGRES_USER': ecs.Secret.from_secrets_manager(aurora_cluster_secret, 'username'),
                'POSTGRES_PASSWORD': ecs.Secret.from_secrets_manager(
                    aurora_cluster_secret, 'password'
                ),
            },
            health_check=ecs.HealthCheck(
                command=['CMD-SHELL', 'curl -f http://localhost:8200/health || exit 1'],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        reservation_container.add_port_mappings(
            ecs.PortMapping(container_port=8200, protocol=ecs.Protocol.TCP)
        )

        # Add ADOT Collector sidecar for seat-reservation-service
        reservation_adot_container = reservation_task_def.add_container(
            'ADOTCollector',
            image=ecs.ContainerImage.from_registry(
                'public.ecr.aws/aws-observability/aws-otel-collector:latest'
            ),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='adot-collector-reservation',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'AWS_REGION': 'us-west-2',  # Set region for ADOT Collector
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
            memory_reservation_mib=256,  # Reserve 256MB for ADOT
        )

        reservation_adot_container.add_port_mappings(
            ecs.PortMapping(container_port=4317, protocol=ecs.Protocol.TCP)
        )

        # Create Fargate service for seat reservation
        reservation_service = ecs.FargateService(
            self,
            'ReservationService',
            cluster=cluster,
            task_definition=reservation_task_def,
            desired_count=4,  # Start with 4 tasks
            min_healthy_percent=50,
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            cloud_map_options=ecs.CloudMapOptions(
                name='seat-reservation-service',
                cloud_map_namespace=namespace,
                dns_record_type=servicediscovery.DnsRecordType.A,
            ),
        )

        # Security groups for Aurora, MSK, Kvrocks already allow VPC traffic
        # No need to modify them here (prevents cyclic dependencies)

        # Auto-scaling for reservation service
        reservation_scaling = reservation_service.auto_scale_task_count(
            min_capacity=4, max_capacity=16
        )
        reservation_scaling.scale_on_cpu_utilization(
            'ReservationCPUScaling', target_utilization_percent=70
        )
        reservation_scaling.scale_on_memory_utilization(
            'ReservationMemoryScaling', target_utilization_percent=80
        )

        # Add reservation service to ALB
        listener.add_targets(
            'ReservationTargets',
            port=8200,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[reservation_service],
            health_check=elbv2.HealthCheck(path='/health', interval=Duration.seconds(30)),
            deregistration_delay=Duration.seconds(30),
            priority=20,
            conditions=[elbv2.ListenerCondition.path_patterns(['/api/reservation/*'])],
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'ALBEndpoint',
            value=f'http://{alb.load_balancer_dns_name}',
            description='Application Load Balancer endpoint',
            export_name='TicketingALBEndpoint',
        )

        CfnOutput(
            self,
            'ClusterName',
            value=cluster.cluster_name,
            description='ECS Cluster name',
        )

        CfnOutput(
            self,
            'TicketingServiceName',
            value=ticketing_service.service_name,
            description='Ticketing service name',
        )

        CfnOutput(
            self,
            'ReservationServiceName',
            value=reservation_service.service_name,
            description='Seat reservation service name',
        )

        # Store references
        self.cluster = cluster
        self.alb = alb
        self.ticketing_service = ticketing_service
        self.reservation_service = reservation_service
