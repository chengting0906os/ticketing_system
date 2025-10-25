"""
ECS Base Stack - Provides ECS Cluster, ALB, and Service Discovery for application services

This stack creates the shared infrastructure needed by application services:
- ECS Cluster (Fargate)
- Application Load Balancer (ALB)
- Service Discovery namespace (Cloud Map)

It depends on a VPC being created by another stack (typically ScyllaDB stack).
"""

from aws_cdk import (
    CfnOutput,
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_servicediscovery as servicediscovery,
)
from constructs import Construct


class ECSBaseStack(Stack):
    """
    ECS Base Infrastructure Stack

    Provides:
    - ECS Cluster with Fargate capacity provider
    - Application Load Balancer for HTTP/HTTPS traffic
    - Service Discovery namespace for inter-service communication
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        **kwargs,
    ) -> None:
        """
        Initialize ECS Base Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC for ECS resources
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # ============= ECS Cluster =============
        self.ecs_cluster = ecs.Cluster(
            self,
            'ECSCluster',
            vpc=vpc,
            container_insights=True,  # Enable CloudWatch Container Insights
        )

        # ============= Application Load Balancer =============
        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            'ALB',
            vpc=vpc,
            internet_facing=True,
            load_balancer_name='ticketing-alb',
        )

        # HTTP listener (redirect to HTTPS in production)
        http_listener = self.alb.add_listener(
            'HttpListener',
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
        )

        # Default target group (will be replaced by services)
        http_listener.add_action(
            'DefaultAction',
            action=elbv2.ListenerAction.fixed_response(
                status_code=404,
                content_type='text/plain',
                message_body='Not Found - No service configured for this path',
            ),
        )

        # Store listener for service registration
        self.alb_listener = http_listener

        # ============= Service Discovery Namespace =============
        # Private DNS namespace for inter-service communication
        self.namespace = servicediscovery.PrivateDnsNamespace(
            self,
            'ServiceDiscoveryNamespace',
            name='ticketing.local',
            vpc=vpc,
            description='Service discovery namespace for ticketing system',
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'ECSClusterName',
            value=self.ecs_cluster.cluster_name,
            description='ECS Cluster name',
        )

        CfnOutput(
            self,
            'ECSClusterArn',
            value=self.ecs_cluster.cluster_arn,
            description='ECS Cluster ARN',
        )

        CfnOutput(
            self,
            'ALBDnsName',
            value=self.alb.load_balancer_dns_name,
            description='Application Load Balancer DNS name',
        )

        CfnOutput(
            self,
            'ALBArn',
            value=self.alb.load_balancer_arn,
            description='Application Load Balancer ARN',
        )

        CfnOutput(
            self,
            'ServiceDiscoveryNamespaceName',
            value=self.namespace.namespace_name,
            description='Service Discovery namespace',
        )
