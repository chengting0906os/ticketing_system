"""
VPC Stack for Ticketing System

This stack creates the foundational network infrastructure:
- VPC with 3 availability zones
- Public, Private, and Database subnets
- Security groups for application, database, and RDS Proxy
- NAT gateways for private subnet internet access

By separating VPC into its own stack, we:
1. Avoid cyclic dependencies between Aurora and ECS stacks
2. Enable independent management of network resources
3. Follow AWS best practices for infrastructure organization
"""

from aws_cdk import CfnOutput, Stack, aws_ec2 as ec2
from constructs import Construct


class VpcStack(Stack):
    """
    Network infrastructure stack for ticketing system

    Creates a multi-AZ VPC with proper subnet segmentation
    and security group configuration for all services.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============= VPC Configuration =============
        self.vpc = ec2.Vpc(
            self,
            'TicketingVpc',
            max_azs=3,  # Use 3 AZs for high availability
            nat_gateways=2,  # 2 NAT gateways for redundancy
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name='Public',
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name='Private',
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name='Database',
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # ============= Security Groups =============

        # Database security group
        self.db_security_group = ec2.SecurityGroup(
            self,
            'DatabaseSecurityGroup',
            vpc=self.vpc,
            description='Security group for Aurora PostgreSQL cluster',
            allow_all_outbound=False,
        )

        # RDS Proxy security group
        self.proxy_security_group = ec2.SecurityGroup(
            self,
            'RdsProxySecurityGroup',
            vpc=self.vpc,
            description='Security group for RDS Proxy',
            allow_all_outbound=True,
        )

        # Application security group (for ECS tasks)
        self.app_security_group = ec2.SecurityGroup(
            self,
            'ApplicationSecurityGroup',
            vpc=self.vpc,
            description='Security group for application (ECS tasks)',
            allow_all_outbound=True,
        )

        # ============= Security Group Rules =============
        # NOTE: Security group rules are NOT defined here to avoid cyclic dependencies.
        # Each consuming stack (Aurora, ECS) will add its own ingress/egress rules
        # using the connections API after the resources are created.

        # ============= Outputs =============
        CfnOutput(
            self,
            'VpcId',
            value=self.vpc.vpc_id,
            description='VPC ID for ticketing system',
        )

        CfnOutput(
            self,
            'DbSecurityGroupId',
            value=self.db_security_group.security_group_id,
            description='Database security group ID',
        )

        CfnOutput(
            self,
            'ProxySecurityGroupId',
            value=self.proxy_security_group.security_group_id,
            description='RDS Proxy security group ID',
        )

        CfnOutput(
            self,
            'AppSecurityGroupId',
            value=self.app_security_group.security_group_id,
            description='Application security group ID',
        )
