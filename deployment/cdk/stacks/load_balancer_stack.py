"""
Load Balancer Stack for Ticketing System
Manages Application Load Balancer for distributing traffic across service instances
"""

from aws_cdk import (
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
)
from constructs import Construct


class LoadBalancerStack(Stack):
    """
    Creates Application Load Balancer for microservices

    Architecture:
        API Gateway → ALB → Target Groups → ECS Services
                      ↓
                   Health Checks

    Benefits:
        - Health checks for automatic failover
        - Support for multiple service instances
        - SSL/TLS termination
        - Connection draining
        - Sticky sessions (if needed)
    """

    def __init__(
        self, scope: Construct, construct_id: str, vpc: ec2.IVpc | None = None, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============= VPC Setup =============

        # Use provided VPC or create new one
        if vpc is None:
            vpc = ec2.Vpc(
                self,
                'LoadBalancerVpc',
                max_azs=2,  # Use 2 availability zones for HA
                nat_gateways=1,
                subnet_configuration=[
                    ec2.SubnetConfiguration(
                        name='Public', subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                    ),
                    ec2.SubnetConfiguration(
                        name='Private',
                        subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                        cidr_mask=24,
                    ),
                ],
            )

        # ============= Application Load Balancer =============

        # Create ALB in public subnets
        alb = elbv2.ApplicationLoadBalancer(
            self,
            'TicketingALB',
            vpc=vpc,
            internet_facing=True,  # Publicly accessible
            load_balancer_name='ticketing-system-alb',
            deletion_protection=False,  # Set to True in production
            # Performance settings
            idle_timeout=Duration.seconds(60),
            # Cross-zone load balancing for better distribution
            cross_zone_enabled=True,
        )

        # ============= Security Group =============

        # ALB security group - allow HTTP/HTTPS from anywhere
        alb_sg = ec2.SecurityGroup(
            self,
            'ALBSecurityGroup',
            vpc=vpc,
            description='Security group for ALB - allows HTTP/HTTPS traffic',
            allow_all_outbound=True,
        )

        # Allow HTTP traffic
        alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(), connection=ec2.Port.tcp(80), description='Allow HTTP'
        )

        # Allow HTTPS traffic
        alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(), connection=ec2.Port.tcp(443), description='Allow HTTPS'
        )

        # ============= Target Groups =============

        # Ticketing Service Target Group (port 8000)
        ticketing_tg = elbv2.ApplicationTargetGroup(
            self,
            'TicketingServiceTG',
            vpc=vpc,
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,  # For ECS Fargate
            target_group_name='ticketing-service-tg',
            # Health check configuration
            health_check=elbv2.HealthCheck(
                enabled=True,
                path='/health',  # Your health check endpoint
                protocol=elbv2.Protocol.HTTP,
                port='8000',
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30),
                # Expected response codes
                healthy_http_codes='200',
            ),
            # Deregistration delay (connection draining)
            deregistration_delay=Duration.seconds(30),
            # Stickiness (optional - disable for stateless services)
            stickiness_cookie_duration=Duration.hours(1),
            stickiness_cookie_name='TICKETING_SESSION',
        )

        # Seat Reservation Service Target Group (port 8001)
        seat_reservation_tg = elbv2.ApplicationTargetGroup(
            self,
            'SeatReservationServiceTG',
            vpc=vpc,
            port=8001,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            target_group_name='seat-reservation-tg',
            health_check=elbv2.HealthCheck(
                enabled=True,
                path='/health',
                protocol=elbv2.Protocol.HTTP,
                port='8001',
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30),
                healthy_http_codes='200',
            ),
            deregistration_delay=Duration.seconds(30),
            stickiness_cookie_duration=Duration.hours(1),
            stickiness_cookie_name='RESERVATION_SESSION',
        )

        # ============= HTTP Listener (Port 80) =============

        # Create HTTP listener
        http_listener = alb.add_listener(
            'HttpListener',
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            # Default action - return 404 for unmatched routes
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=404,
                content_type='application/json',
                message_body='{"error": "Route not found"}',
            ),
        )

        # ============= Listener Rules (Path-based routing) =============

        # Rule 1: /api/user/* → Ticketing Service
        http_listener.add_target_groups(
            'TicketingUserRule',
            target_groups=[ticketing_tg],
            priority=40,
            conditions=[elbv2.ListenerCondition.path_patterns(['/api/user*'])],
        )

        # Rule 2: /api/event/* → Ticketing Service
        http_listener.add_target_groups(
            'TicketingEventRule',
            target_groups=[ticketing_tg],
            priority=30,
            conditions=[elbv2.ListenerCondition.path_patterns(['/api/event*'])],
        )

        # Rule 3: /api/booking/* → Ticketing Service
        http_listener.add_target_groups(
            'TicketingBookingRule',
            target_groups=[ticketing_tg],
            priority=10,
            conditions=[elbv2.ListenerCondition.path_patterns(['/api/booking*'])],
        )

        # Rule 4: /api/reservation/* → Seat Reservation Service
        http_listener.add_target_groups(
            'SeatReservationRule',
            target_groups=[seat_reservation_tg],
            priority=20,
            conditions=[elbv2.ListenerCondition.path_patterns(['/api/reservation*'])],
        )

        # Rule 5: /health → ALB health check
        http_listener.add_action(
            'HealthCheckRule',
            priority=50,
            conditions=[elbv2.ListenerCondition.path_patterns(['/health'])],
            action=elbv2.ListenerAction.fixed_response(
                status_code=200,
                content_type='application/json',
                message_body='{"status": "healthy", "service": "alb"}',
            ),
        )

        # ============= Outputs =============

        from aws_cdk import CfnOutput

        CfnOutput(
            self,
            'LoadBalancerDNS',
            value=alb.load_balancer_dns_name,
            description='Application Load Balancer DNS name',
        )

        CfnOutput(
            self,
            'LoadBalancerArn',
            value=alb.load_balancer_arn,
            description='Application Load Balancer ARN',
        )

        CfnOutput(
            self,
            'TicketingTargetGroupArn',
            value=ticketing_tg.target_group_arn,
            description='Ticketing Service Target Group ARN',
        )

        CfnOutput(
            self,
            'SeatReservationTargetGroupArn',
            value=seat_reservation_tg.target_group_arn,
            description='Seat Reservation Service Target Group ARN',
        )

        # Export properties for other stacks
        self.load_balancer = alb
        self.ticketing_target_group = ticketing_tg
        self.seat_reservation_target_group = seat_reservation_tg
        self.vpc = vpc
        self.alb_security_group = alb_sg


class LoadBalancerStackForLocalStack(Stack):
    """
    Simplified Load Balancer for LocalStack testing

    Note: LocalStack's ALB support is limited. For local testing,
    consider using docker-compose with nginx as a reverse proxy instead.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        from aws_cdk import CfnOutput

        CfnOutput(
            self,
            'Note',
            value='For local development, use docker-compose with nginx',
            description='LocalStack ALB support is experimental',
        )

        # TODO: If LocalStack ALB support improves, add minimal config here
        # For now, recommend using docker-compose.yml with nginx
