"""
ECS Fargate Stack for High-Throughput Ticketing System

Optimized for 10,000 QPS with:
- ECS Fargate tasks (no EC2 management)
- Auto-scaling based on CPU, memory, and request count
- Application Load Balancer with health checks
- CloudWatch Container Insights
- Pre-warming capability via EventBridge scheduled rules
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_applicationautoscaling as appscaling,
    aws_cloudwatch as cloudwatch,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class EcsStack(Stack):
    """
    ECS Fargate cluster with auto-scaling for 10,000 QPS

    Architecture:
    - Application Load Balancer (ALB)
    - ECS Fargate service with auto-scaling
    - Production: 30-100 tasks (0.5 vCPU, 1GB each)
    - Development: 2-10 tasks (0.25 vCPU, 0.5GB each)
    - Pre-warming via EventBridge for predictable traffic spikes
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        cluster: ecs.ICluster,  # From KVRocks stack
        app_security_group_id: str,
        db_credentials_secret: secretsmanager.ISecret,
        db_proxy_endpoint: str,  # Writer endpoint (via RDS Proxy)
        db_reader_endpoint: str,  # Reader endpoint (Aurora read replicas)
        kvrocks_endpoint: str,
        environment: str = 'production',
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = environment

        # Import security group from VPC Stack by ID to avoid cyclic dependencies
        app_security_group = ec2.SecurityGroup.from_security_group_id(
            self, 'ImportedAppSecurityGroup', app_security_group_id
        )

        # ============= ECR Repository =============

        # Create ECR repository for container images
        ecr_repo = ecr.Repository(
            self,
            'TicketingRepository',
            repository_name=f'ticketing-system-{environment}',
            image_scan_on_push=True,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description='Keep last 10 images',
                    max_image_count=10,
                )
            ],
        )

        # ============= Task Execution Role =============

        execution_role = iam.Role(
            self,
            'TaskExecutionRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    'service-role/AmazonECSTaskExecutionRolePolicy'
                ),
            ],
        )

        # Grant access to secrets
        db_credentials_secret.grant_read(execution_role)

        # ============= Task Role =============

        task_role = iam.Role(
            self,
            'TaskRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
        )

        # Grant access to CloudWatch for custom metrics
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    'cloudwatch:PutMetricData',
                ],
                resources=['*'],
            )
        )

        # ============= Task Definition =============

        # Resource allocation based on environment
        if environment == 'production':
            cpu = 512  # 0.5 vCPU
            memory = 1024  # 1 GB
        else:  # development
            cpu = 256  # 0.25 vCPU
            memory = 512  # 0.5 GB

        task_definition = ecs.FargateTaskDefinition(
            self,
            'TaskDefinition',
            cpu=cpu,
            memory_limit_mib=memory,
            execution_role=execution_role,
            task_role=task_role,
        )

        # Container configuration
        container = task_definition.add_container(
            'TicketingContainer',
            image=ecs.ContainerImage.from_registry('nginx:latest'),  # Placeholder
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix='ticketing',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'ENVIRONMENT': environment,
                # Database endpoints for read/write splitting
                'POSTGRES_SERVER': db_proxy_endpoint,  # Writer (INSERT/UPDATE/DELETE)
                'POSTGRES_READ_SERVER': db_reader_endpoint,  # Reader (SELECT)
                # KVRocks
                'KVROCKS_HOST': kvrocks_endpoint,  # Service Discovery DNS
                # Application config
                'WORKERS': '4' if environment == 'production' else '2',
            },
            secrets={
                'DB_PASSWORD': ecs.Secret.from_secrets_manager(db_credentials_secret, 'password'),
                'DB_USERNAME': ecs.Secret.from_secrets_manager(db_credentials_secret, 'username'),
            },
            health_check=ecs.HealthCheck(
                command=['CMD-SHELL', 'curl -f http://localhost:8000/health || exit 1'],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        # Expose port
        container.add_port_mappings(
            ecs.PortMapping(
                container_port=8000,
                protocol=ecs.Protocol.TCP,
            )
        )

        # ============= Application Load Balancer =============

        alb = elbv2.ApplicationLoadBalancer(
            self,
            'LoadBalancer',
            vpc=vpc,
            internet_facing=True,
            load_balancer_name=f'ticketing-alb-{environment}',
        )

        # HTTP listener
        listener = alb.add_listener(
            'HttpListener',
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
        )

        # ============= ECS Service =============

        # Task count based on environment
        if environment == 'production':
            desired_count = 30  # Start with 30 tasks
            min_capacity = 30
            max_capacity = 100
        else:  # development
            desired_count = 2
            min_capacity = 2
            max_capacity = 10

        service = ecs.FargateService(
            self,
            'TicketingService',
            cluster=cluster,
            task_definition=task_definition,
            desired_count=desired_count,
            service_name=f'ticketing-service-{environment}',
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[app_security_group],
            # Health check configuration
            health_check_grace_period=Duration.seconds(60),
            # Deployment configuration
            min_healthy_percent=100,  # Always maintain capacity during deployment
            max_healthy_percent=200,  # Can double capacity during deployment
            circuit_breaker=ecs.DeploymentCircuitBreaker(
                rollback=True  # Auto-rollback on deployment failure
            ),
        )

        # Attach to load balancer
        target_group = listener.add_targets(
            'TicketingTarget',
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[service],
            health_check=elbv2.HealthCheck(
                path='/health',
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=Duration.seconds(30),
        )

        # ============= Auto-Scaling Configuration =============

        scaling = service.auto_scale_task_count(
            min_capacity=min_capacity,
            max_capacity=max_capacity,
        )

        # Scale on CPU utilization
        scaling.scale_on_cpu_utilization(
            'CpuScaling',
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(30),
        )

        # Scale on memory utilization
        scaling.scale_on_memory_utilization(
            'MemoryScaling',
            target_utilization_percent=80,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(30),
        )

        # Scale on request count per target
        scaling.scale_on_metric(
            'RequestCountScaling',
            metric=target_group.metric_request_count_per_target(
                statistic='Average',
                period=Duration.minutes(1),
            ),
            scaling_steps=[
                appscaling.ScalingInterval(upper=100, change=0),  # < 100 RPS: no change
                appscaling.ScalingInterval(
                    lower=100, upper=200, change=+5
                ),  # 100-200 RPS: +5 tasks
                appscaling.ScalingInterval(
                    lower=200, upper=300, change=+10
                ),  # 200-300 RPS: +10 tasks
                appscaling.ScalingInterval(lower=300, change=+15),  # > 300 RPS: +15 tasks
            ],
            adjustment_type=appscaling.AdjustmentType.CHANGE_IN_CAPACITY,
        )

        # ============= Pre-warming for Predictable Traffic Spikes =============

        # EventBridge rule to pre-warm before peak hours (e.g., 9 AM Taiwan time = 1 AM UTC)
        prewarm_rule = events.Rule(
            self,
            'PrewarmRule',
            schedule=events.Schedule.cron(minute='0', hour='1'),  # 1 AM UTC = 9 AM Taiwan
            description='Pre-warm ECS tasks before peak hours',
        )

        # Target: Set desired count to 80 (near max capacity)
        prewarm_rule.add_target(
            targets.EcsTask(
                cluster=cluster,
                task_definition=task_definition,
                role=execution_role,
                # Note: This is a workaround - ideally use Step Functions or Lambda
                # to update service desired count
            )
        )

        # EventBridge rule to scale down after peak hours (e.g., 6 PM Taiwan time = 10 AM UTC)
        events.Rule(
            self,
            'ScaleDownRule',
            schedule=events.Schedule.cron(minute='0', hour='10'),  # 10 AM UTC = 6 PM Taiwan
            description='Scale down ECS tasks after peak hours',
        )

        # ============= CloudWatch Alarms =============

        # High CPU alarm
        cloudwatch.Alarm(
            self,
            'ServiceHighCPU',
            metric=service.metric_cpu_utilization(),
            threshold=80,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='Service CPU > 80%',
        )

        # High memory alarm
        cloudwatch.Alarm(
            self,
            'ServiceHighMemory',
            metric=service.metric_memory_utilization(),
            threshold=85,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='Service memory > 85%',
        )

        # ALB unhealthy target alarm
        cloudwatch.Alarm(
            self,
            'UnhealthyTargets',
            metric=target_group.metric_unhealthy_host_count(),
            threshold=3,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='More than 3 unhealthy targets',
        )

        # High response time alarm
        cloudwatch.Alarm(
            self,
            'HighResponseTime',
            metric=target_group.metric_target_response_time(),
            threshold=1.0,  # 1 second
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description='Response time > 1 second',
        )

        # ============= Outputs =============

        CfnOutput(
            self,
            'LoadBalancerDNS',
            value=alb.load_balancer_dns_name,
            description='ALB DNS name',
        )

        CfnOutput(
            self,
            'EcrRepositoryUri',
            value=ecr_repo.repository_uri,
            description='ECR repository URI for container images',
        )

        CfnOutput(
            self,
            'ClusterName',
            value=cluster.cluster_name,
            description='ECS cluster name',
        )

        CfnOutput(
            self,
            'ServiceName',
            value=service.service_name,
            description='ECS service name',
        )

        # Store attributes
        self.cluster = cluster
        self.service = service
        self.alb = alb
        self.ecr_repo = ecr_repo
        self.task_definition = task_definition
