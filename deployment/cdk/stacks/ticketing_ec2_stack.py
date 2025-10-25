"""
Ticketing Service EC2 Stack
Deploys ticketing-service on EC2 instances (not ECS)

Architecture:
- EC2 instances with Python application
- User data script for automated setup
- ALB for load balancing
- Auto Scaling Group for high availability

Benefits over ECS:
- Full control and easier debugging (SSH access)
- Simpler deployment (no Docker required)
- Lower cost (~$30/month vs ~$60/month for Fargate)
- Can upgrade to ECS later when needed
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_autoscaling as autoscaling,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
)
from constructs import Construct


class TicketingEC2Stack(Stack):
    """
    Ticketing Service on EC2 instances

    Configuration:
    - Instance type: t3.medium (2 vCPU, 4 GB RAM)
    - Auto Scaling: 1-4 instances
    - ALB integration for HTTP traffic
    - Systemd service management
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        alb: elbv2.IApplicationLoadBalancer,
        alb_listener: elbv2.IApplicationListener,
        scylla_contact_points: list[str],
        kvrocks_endpoint: str,
        kafka_bootstrap_servers: str,
        config: dict,
        **kwargs,
    ) -> None:
        """
        Initialize Ticketing Service EC2 Stack

        Args:
            vpc: VPC for EC2 instances
            alb: Application Load Balancer
            alb_listener: ALB listener for routing
            scylla_contact_points: ScyllaDB node IPs
            kvrocks_endpoint: Kvrocks connection endpoint
            kafka_bootstrap_servers: Kafka bootstrap servers
            config: Environment configuration from config.yml
        """
        super().__init__(scope, construct_id, **kwargs)

        # ============= Security Group =============
        self.security_group = ec2.SecurityGroup(
            self,
            'TicketingSecurityGroup',
            vpc=vpc,
            description='Security group for Ticketing Service EC2 instances',
            allow_all_outbound=True,
        )

        # Allow HTTP from ALB
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(8100),
            description='HTTP from ALB',
        )

        # Allow SSH from VPC (for debugging)
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(22),
            description='SSH access',
        )

        # ============= IAM Role =============
        role = iam.Role(
            self,
            'TicketingInstanceRole',
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=[
                # SSM for remote access (no SSH keys needed)
                iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
                # CloudWatch for logs and metrics
                iam.ManagedPolicy.from_aws_managed_policy_name('CloudWatchAgentServerPolicy'),
            ],
        )

        # ============= User Data Script =============
        # Prepare environment variables for user data
        contact_points_json = '[' + ', '.join(f'"{ip}"' for ip in scylla_contact_points) + ']'

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            '#!/bin/bash',
            'set -euo pipefail',
            '',
            '# ============================================================================',
            '# Ticketing Service Installation Script',
            '# ============================================================================',
            'exec > >(tee -a /var/log/ticketing-setup.log)',
            'exec 2>&1',
            'echo "=========================================="',
            'echo "Ticketing Service Setup Started: $(date)"',
            'echo "=========================================="',
            '',
            '# ============================================================================',
            '# Install Dependencies',
            '# ============================================================================',
            'echo ">>> Installing system dependencies..."',
            'dnf install -y git python3.13 python3.13-pip curl',
            '',
            '# Install uv (fast Python package installer)',
            'curl -LsSf https://astral.sh/uv/install.sh | sh',
            'export PATH="/root/.cargo/bin:$PATH"',
            '',
            '# ============================================================================',
            '# Clone Repository',
            '# ============================================================================',
            'echo ">>> Cloning ticketing system repository..."',
            'cd /opt',
            '# TODO: Replace with your actual repo URL',
            '# git clone https://github.com/your-org/ticketing_system.git',
            '# For now, create directory structure',
            'mkdir -p /opt/ticketing_system',
            '',
            '# ============================================================================',
            '# Environment Configuration',
            '# ============================================================================',
            'echo ">>> Creating environment configuration..."',
            'cat > /opt/ticketing_system/.env <<EOF',
            '# Service Configuration',
            'SERVICE_NAME=ticketing-service',
            f'LOG_LEVEL={config["log_level"]}',
            f'WORKERS={config["ecs"]["ticketing"]["workers"]}',
            '',
            '# ScyllaDB Configuration',
            'DATABASE_TYPE=scylladb',
            f'SCYLLA_CONTACT_POINTS={contact_points_json}',
            'SCYLLA_PORT=9042',
            'SCYLLA_KEYSPACE=ticketing_system',
            'SCYLLA_USERNAME=cassandra',
            'SCYLLA_PASSWORD=cassandra',
            '',
            '# Kvrocks Configuration',
            f'KVROCKS_HOST={kvrocks_endpoint}',
            'KVROCKS_PORT=6666',
            '',
            '# Kafka Configuration',
            'ENABLE_KAFKA=false',
            f'KAFKA_BOOTSTRAP_SERVERS={kafka_bootstrap_servers}',
            '',
            '# JWT Configuration',
            'ACCESS_TOKEN_EXPIRE_MINUTES=30',
            'REFRESH_TOKEN_EXPIRE_DAYS=7',
            'SECRET_KEY=of8uBXD-S4KJKvu7-C4KVUSxQICl8fg5eMDXVtvBFPw',
            'ALGORITHM=HS256',
            'EOF',
            '',
            '# ============================================================================',
            '# Install Python Dependencies',
            '# ============================================================================',
            'echo ">>> Installing Python dependencies..."',
            'cd /opt/ticketing_system',
            '# uv sync  # Uncomment when repo is cloned',
            '',
            '# ============================================================================',
            '# Create Systemd Service',
            '# ============================================================================',
            'echo ">>> Creating systemd service..."',
            'cat > /etc/systemd/system/ticketing.service <<EOF',
            '[Unit]',
            'Description=Ticketing Service',
            'After=network.target',
            '',
            '[Service]',
            'Type=simple',
            'User=root',
            'WorkingDirectory=/opt/ticketing_system',
            'Environment="PATH=/root/.cargo/bin:/usr/local/bin:/usr/bin"',
            'EnvironmentFile=/opt/ticketing_system/.env',
            'ExecStart=/root/.cargo/bin/uv run granian src.service.ticketing.main:app --interface asgi --host 0.0.0.0 --port 8100 --workers ${WORKERS}',
            'Restart=always',
            'RestartSec=10',
            '',
            '[Install]',
            'WantedBy=multi-user.target',
            'EOF',
            '',
            '# ============================================================================',
            '# Enable and Start Service',
            '# ============================================================================',
            'echo ">>> Enabling ticketing service..."',
            'systemctl daemon-reload',
            'systemctl enable ticketing.service',
            '# systemctl start ticketing.service  # Uncomment when app is ready',
            '',
            '# ============================================================================',
            '# Health Check Endpoint',
            '# ============================================================================',
            'echo ">>> Waiting for service to start..."',
            '# for i in {1..30}; do',
            '#     if curl -f http://localhost:8100/health > /dev/null 2>&1; then',
            '#         echo "Service is healthy!"',
            '#         break',
            '#     fi',
            '#     echo "Waiting for service... ($i/30)"',
            '#     sleep 2',
            '# done',
            '',
            '# ============================================================================',
            '# Completion',
            '# ============================================================================',
            'echo "=========================================="',
            'echo "Ticketing Service Setup Completed: $(date)"',
            'echo "=========================================="',
            'echo ""',
            'echo "Next steps:"',
            'echo "1. Clone your repository to /opt/ticketing_system"',
            'echo "2. Run: uv sync"',
            'echo "3. Start service: systemctl start ticketing.service"',
            'echo "4. Check status: systemctl status ticketing.service"',
            'echo "5. View logs: journalctl -u ticketing.service -f"',
            'echo "=========================================="',
        )

        # ============= Launch Template =============
        launch_template = ec2.LaunchTemplate(
            self,
            'TicketingLaunchTemplate',
            instance_type=ec2.InstanceType('t3.medium'),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                edition=ec2.AmazonLinuxEdition.STANDARD,
                cpu_type=ec2.AmazonLinuxCpuType.X86_64,
            ),
            security_group=self.security_group,
            role=role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name='/dev/xvda',
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=20,  # 20 GB for app + dependencies
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                ),
            ],
            detailed_monitoring=True,
        )

        # ============= Auto Scaling Group =============
        asg = autoscaling.AutoScalingGroup(
            self,
            'TicketingASG',
            vpc=vpc,
            launch_template=launch_template,
            min_capacity=config['ecs']['min_tasks'],
            max_capacity=config['ecs']['max_tasks'],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            health_check=autoscaling.HealthCheck.elb(grace=Duration.minutes(5)),
        )

        # CPU-based scaling
        asg.scale_on_cpu_utilization(
            'CPUScaling',
            target_utilization_percent=config['ecs']['cpu_threshold'],
        )

        # ============= ALB Target Group =============
        target_group = elbv2.ApplicationTargetGroup(
            self,
            'TicketingTargetGroup',
            vpc=vpc,
            port=8100,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[asg],
            health_check=elbv2.HealthCheck(
                path='/health',
                interval=Duration.seconds(30),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
                timeout=Duration.seconds(5),
            ),
            deregistration_delay=Duration.seconds(30),
        )

        # Add target group to ALB listener
        alb_listener.add_target_groups(
            'TicketingTargets',
            target_groups=[target_group],
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
            'AutoScalingGroupName',
            value=asg.auto_scaling_group_name,
            description='Auto Scaling Group name',
        )

        CfnOutput(
            self,
            'TargetGroupArn',
            value=target_group.target_group_arn,
            description='Target Group ARN',
        )

        CfnOutput(
            self,
            'SSHInstructions',
            value='aws ssm start-session --target <instance-id>',
            description='Connect to instance via AWS Systems Manager',
        )

        # Store references
        self.asg = asg
        self.target_group = target_group
