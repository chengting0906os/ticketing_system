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
- Each service: 4-16 tasks (auto-scaling)
- Each task: 2 vCPU + 4GB RAM
- Total capacity: 8-32 vCPU, 16-64GB RAM
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
        aurora_security_group: ec2.ISecurityGroup,
        msk_security_group: ec2.ISecurityGroup,
        kvrocks_security_group: ec2.ISecurityGroup,
        **kwargs,
    ) -> None:
        """
        Initialize ECS Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC for ECS tasks
            aurora_security_group: Aurora security group (for database access)
            msk_security_group: MSK security group (for Kafka access)
            kvrocks_security_group: Kvrocks security group (for cache access)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

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
        # Private DNS namespace for service-to-service communication
        namespace = servicediscovery.PrivateDnsNamespace(
            self,
            'ServiceDiscovery',
            name='ticketing.local',
            vpc=vpc,
            description='Service discovery for ticketing system',
        )

        # ============= ECR Repositories =============
        # Container image repositories
        ticketing_repo = ecr.Repository(
            self,
            'TicketingServiceRepo',
            repository_name='ticketing-service',
            image_scan_on_push=True,  # Scan for vulnerabilities
        )

        reservation_repo = ecr.Repository(
            self,
            'ReservationServiceRepo',
            repository_name='seat-reservation-service',
            image_scan_on_push=True,
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

        # ============= Ticketing Service =============
        ticketing_task_def = ecs.FargateTaskDefinition(
            self,
            'TicketingTaskDef',
            memory_limit_mib=4096,  # 4GB RAM
            cpu=2048,  # 2 vCPU
            execution_role=execution_role,
            task_role=task_role,
        )

        ticketing_container = ticketing_task_def.add_container(
            'TicketingContainer',
            image=ecs.ContainerImage.from_ecr_repository(ticketing_repo, tag='latest'),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='ticketing',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'SERVICE_NAME': 'ticketing-service',
                'LOG_LEVEL': 'INFO',
            },
            # Secrets will be injected from Secrets Manager at runtime
            health_check=ecs.HealthCheck(
                command=['CMD-SHELL', 'curl -f http://localhost:8000/health || exit 1'],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        ticketing_container.add_port_mappings(
            ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
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

        # Allow ticketing service to access Aurora, MSK, Kvrocks
        aurora_security_group.add_ingress_rule(
            peer=ticketing_service.connections.security_groups[0],
            connection=ec2.Port.tcp(5432),
            description='Ticketing service to Aurora',
        )
        msk_security_group.add_ingress_rule(
            peer=ticketing_service.connections.security_groups[0],
            connection=ec2.Port.tcp_range(9092, 9098),
            description='Ticketing service to MSK',
        )
        kvrocks_security_group.add_ingress_rule(
            peer=ticketing_service.connections.security_groups[0],
            connection=ec2.Port.tcp(6666),
            description='Ticketing service to Kvrocks',
        )

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
            port=8000,
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
            logging=ecs.LogDriver.aws_logs(
                stream_prefix='reservation',
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                'SERVICE_NAME': 'seat-reservation-service',
                'LOG_LEVEL': 'INFO',
            },
            health_check=ecs.HealthCheck(
                command=['CMD-SHELL', 'curl -f http://localhost:8001/health || exit 1'],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        reservation_container.add_port_mappings(
            ecs.PortMapping(container_port=8001, protocol=ecs.Protocol.TCP)
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

        # Allow reservation service to access Aurora, MSK, Kvrocks
        aurora_security_group.add_ingress_rule(
            peer=reservation_service.connections.security_groups[0],
            connection=ec2.Port.tcp(5432),
            description='Reservation service to Aurora',
        )
        msk_security_group.add_ingress_rule(
            peer=reservation_service.connections.security_groups[0],
            connection=ec2.Port.tcp_range(9092, 9098),
            description='Reservation service to MSK',
        )
        kvrocks_security_group.add_ingress_rule(
            peer=reservation_service.connections.security_groups[0],
            connection=ec2.Port.tcp(6666),
            description='Reservation service to Kvrocks',
        )

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
            port=8001,
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
