"""
EC2 Load Test Stack for Ticketing System
Runs load testing using Docker on a single EC2 instance

Architecture:
- EC2 instance with Docker installed
- SSH/SSM access for direct shell operations
- Uses loadtest-service ECR image (Alpine + Go binaries)
- Runs inside VPC to access ALB/Aurora/Kvrocks/Kafka

Usage:
1. Deploy stack: `DEPLOY_ENV=development uv run cdk deploy TicketingLoadTestStack`
2. SSH into instance: `aws ssm start-session --target <instance-id>`
3. Run loadtest: `cd /home/ec2-user && docker exec -it loadtest sh`
4. Inside container: `cd script/go_client && make frlt WORKERS=500 BATCH=1`

Cost:
- c7i.xlarge (4 vCPU, 8GB): ~$0.17/hour (~$122/month if running 24/7)
- Stop instance when not in use to save cost
"""

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class LoadTestStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        alb_dns: str,
        aurora_cluster_endpoint: str,
        aurora_cluster_secret: secretsmanager.ISecret,
        app_secrets: secretsmanager.ISecret,
        kafka_bootstrap_servers: str,
        kvrocks_endpoint: str,
        config: dict,
        **kwargs,
    ) -> None:
        """
        Initialize EC2 Load Test Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC (must be same as ECS services for internal testing)
            alb_dns: ALB internal DNS name
            aurora_cluster_endpoint: Aurora endpoint for seed operations
            aurora_cluster_secret: Aurora credentials
            app_secrets: Shared JWT secrets
            kafka_bootstrap_servers: Kafka bootstrap servers
            kvrocks_endpoint: Kvrocks endpoint (host:port)
            config: Configuration dict from config.yml
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Extract loadtest configuration
        loadtest_config = config.get('loadtest', {})
        instance_type_str = loadtest_config.get('instance_type', 'c7i.xlarge')
        storage_gb = loadtest_config.get('storage_gb', 50)
        environment = config.get('environment', 'development')

        # Parse Kvrocks endpoint
        kvrocks_host, kvrocks_port = kvrocks_endpoint.split(':')

        # Determine CPU architecture based on instance type
        is_arm = any(
            instance_type_str.startswith(prefix)
            for prefix in ['t4g', 'm6g', 'm7g', 'c6g', 'c7g', 'r6g', 'r7g']
        )
        cpu_type = ec2.AmazonLinuxCpuType.ARM_64 if is_arm else ec2.AmazonLinuxCpuType.X86_64

        # ============= ECR Repository =============
        loadtest_repo = ecr.Repository.from_repository_name(
            self, 'LoadTestServiceRepo', repository_name='loadtest-service'
        )

        # ============= IAM Role for EC2 Instance =============
        instance_role = iam.Role(
            self,
            'LoadTestInstanceRole',
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            description='IAM role for LoadTest EC2 instance',
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    'AmazonEC2ContainerRegistryReadOnly'
                ),
            ],
        )

        # Grant access to Aurora and App secrets
        aurora_cluster_secret.grant_read(instance_role)
        app_secrets.grant_read(instance_role)

        # Grant permissions for running AWS operations inside container
        instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    'ec2:DescribeSubnets',
                    'ec2:DescribeSecurityGroups',
                    'ec2:DescribeInstances',
                    'ecs:DescribeServices',
                    'ecs:DescribeTaskDefinition',
                    'ecs:RunTask',
                    'ecs:ListTasks',
                    'ecs:DescribeTasks',
                    'ecs:ListServices',
                    'ecs:UpdateService',
                    'autoscaling:DescribeAutoScalingGroups',
                    'autoscaling:SetDesiredCapacity',
                    'ssm:SendCommand',
                    'ssm:GetCommandInvocation',
                    'ssm:GetParameter',
                    'rds:DescribeDBClusters',
                    'rds:ModifyDBCluster',
                ],
                resources=['*'],
                effect=iam.Effect.ALLOW,
            )
        )

        # Grant permission to pass ECS task execution role
        instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=['iam:PassRole'],
                resources=[f'arn:aws:iam::{self.account}:role/*'],
                conditions={'StringLike': {'iam:PassedToService': 'ecs-tasks.amazonaws.com'}},
                effect=iam.Effect.ALLOW,
            )
        )

        # ============= Security Group =============
        loadtest_sg = ec2.SecurityGroup(
            self,
            'LoadTestSG',
            vpc=vpc,
            description='Security group for load test EC2 instance',
            allow_all_outbound=True,
        )

        # SSH access from VPC (for debugging)
        loadtest_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(22),
            description='SSH access from VPC',
        )

        # ============= CloudWatch Log Group =============
        log_group = logs.LogGroup(
            self,
            'LoadTestLogs',
            log_group_name=f'/ec2/loadtest-{environment}',
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ============= User Data Script =============
        user_data = self._create_user_data(
            alb_dns=alb_dns,
            aurora_endpoint=aurora_cluster_endpoint,
            aurora_secret_arn=aurora_cluster_secret.secret_arn,
            app_secrets_arn=app_secrets.secret_arn,
            kafka_bootstrap_servers=kafka_bootstrap_servers,
            kvrocks_host=kvrocks_host,
            kvrocks_port=kvrocks_port,
            environment=environment,
            debug=str(config.get('debug', False)).lower(),
            is_arm=is_arm,
        )

        # ============= Block Device (EBS) =============
        block_devices = [
            ec2.BlockDevice(
                device_name='/dev/xvda',
                volume=ec2.BlockDeviceVolume.ebs(
                    volume_size=storage_gb,
                    volume_type=ec2.EbsDeviceVolumeType.GP3,
                    delete_on_termination=True,
                    encrypted=True,
                ),
            ),
        ]

        # ============= EC2 Instance =============
        private_subnets = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnets

        instance = ec2.Instance(
            self,
            'LoadTestInstance',
            instance_name=f'loadtest-{environment}',
            instance_type=ec2.InstanceType(instance_type_str),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(cpu_type=cpu_type),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[private_subnets[0]]),
            security_group=loadtest_sg,
            user_data=user_data,
            block_devices=block_devices,
            role=instance_role,
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'InstanceId',
            value=instance.instance_id,
            description='EC2 Instance ID for SSM session',
            export_name='LoadTestInstanceId',
        )

        CfnOutput(
            self,
            'InstancePrivateIP',
            value=instance.instance_private_ip,
            description='EC2 Instance Private IP',
            export_name='LoadTestInstancePrivateIP',
        )

        CfnOutput(
            self,
            'SSMCommand',
            value=f'aws ssm start-session --target {instance.instance_id}',
            description='Command to SSH into the instance via SSM',
        )

        CfnOutput(
            self,
            'ECRRepository',
            value=loadtest_repo.repository_uri,
            description='ECR repository for loadtest image',
            export_name='LoadTestECRRepository',
        )

        CfnOutput(
            self,
            'SecurityGroupId',
            value=loadtest_sg.security_group_id,
            description='Security Group ID for loadtest instance',
            export_name='LoadTestSecurityGroupId',
        )

        CfnOutput(
            self,
            'LogGroupName',
            value=log_group.log_group_name,
            description='CloudWatch Log Group for loadtest',
        )

        # Store references
        self.instance = instance
        self.security_group = loadtest_sg
        self.ecr_repository = loadtest_repo

    def _create_user_data(
        self,
        *,
        alb_dns: str,
        aurora_endpoint: str,
        aurora_secret_arn: str,
        app_secrets_arn: str,
        kafka_bootstrap_servers: str,
        kvrocks_host: str,
        kvrocks_port: str,
        environment: str,
        debug: str,
        is_arm: bool = False,
    ) -> ec2.UserData:
        """Create user data script to install Go, k6, and Python directly on EC2"""
        user_data = ec2.UserData.for_linux()

        # Determine architecture for downloads
        go_arch = 'arm64' if is_arm else 'amd64'
        k6_arch = 'arm64' if is_arm else 'amd64'

        user_data.add_commands(
            '#!/bin/bash',
            'set -ex',
            '',
            '# ============= System Setup =============',
            'dnf update -y',
            'dnf install -y git jq gcc g++ make tar gzip curl wget librdkafka-devel',
            '',
            '# ============= Get Instance Metadata (IMDSv2) =============',
            'TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")',
            'REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)',
            'echo "Region: $REGION"',
            '',
            '# ============= Install Go =============',
            'GO_VERSION=1.25.4',
            f'wget -q https://go.dev/dl/go${{GO_VERSION}}.linux-{go_arch}.tar.gz',
            f'tar -C /usr/local -xzf go${{GO_VERSION}}.linux-{go_arch}.tar.gz',
            f'rm go${{GO_VERSION}}.linux-{go_arch}.tar.gz',
            'echo "export PATH=/usr/local/go/bin:\\$PATH" >> /etc/profile.d/go.sh',
            'echo "export GOPATH=/home/ec2-user/go" >> /etc/profile.d/go.sh',
            'echo "export PATH=\\$GOPATH/bin:\\$PATH" >> /etc/profile.d/go.sh',
            'source /etc/profile.d/go.sh',
            '/usr/local/go/bin/go version',
            '',
            '# ============= Install k6 =============',
            'K6_VERSION=v1.4.2',
            f'wget -q https://github.com/grafana/k6/releases/download/${{K6_VERSION}}/k6-${{K6_VERSION}}-linux-{k6_arch}.tar.gz',
            f'tar -xzf k6-${{K6_VERSION}}-linux-{k6_arch}.tar.gz',
            f'mv k6-${{K6_VERSION}}-linux-{k6_arch}/k6 /usr/local/bin/',
            f'rm -rf k6-${{K6_VERSION}}-linux-{k6_arch}*',
            'k6 version',
            '',
            '# ============= Install Python & uv =============',
            'dnf install -y python3.11 python3.11-pip',
            'curl -LsSf https://astral.sh/uv/install.sh | sh',
            'echo "export PATH=/root/.local/bin:\\$PATH" >> /etc/profile.d/uv.sh',
            'source /etc/profile.d/uv.sh',
            '',
            '# ============= Get Secrets from Secrets Manager =============',
            f'AURORA_SECRET=$(aws secretsmanager get-secret-value --secret-id {aurora_secret_arn} --region $REGION --query SecretString --output text)',
            'POSTGRES_USER=$(echo $AURORA_SECRET | jq -r .username)',
            'POSTGRES_PASSWORD=$(echo $AURORA_SECRET | jq -r .password)',
            '',
            f'APP_SECRET=$(aws secretsmanager get-secret-value --secret-id {app_secrets_arn} --region $REGION --query SecretString --output text)',
            'SECRET_KEY=$(echo $APP_SECRET | jq -r .SECRET_KEY)',
            'RESET_PASSWORD_TOKEN_SECRET=$(echo $APP_SECRET | jq -r .RESET_PASSWORD_TOKEN_SECRET)',
            'VERIFICATION_TOKEN_SECRET=$(echo $APP_SECRET | jq -r .VERIFICATION_TOKEN_SECRET)',
            'ALGORITHM=$(echo $APP_SECRET | jq -r .ALGORITHM)',
            '',
            '# ============= Create Environment File =============',
            'cat > /home/ec2-user/.env << EOF',
            f'ALB_HOST=http://{alb_dns}',
            f'API_HOST=http://{alb_dns}',
            'AWS_REGION=$REGION',
            f'POSTGRES_SERVER={aurora_endpoint}',
            'POSTGRES_DB=ticketing_system_db',
            'POSTGRES_PORT=5432',
            'POSTGRES_USER=$POSTGRES_USER',
            'POSTGRES_PASSWORD=$POSTGRES_PASSWORD',
            f'KAFKA_BOOTSTRAP_SERVERS={kafka_bootstrap_servers}',
            f'KVROCKS_HOST={kvrocks_host}',
            f'KVROCKS_PORT={kvrocks_port}',
            f'DEBUG={debug}',
            f'DEPLOY_ENV={environment}',
            'ACCESS_TOKEN_EXPIRE_MINUTES=30',
            'REFRESH_TOKEN_EXPIRE_DAYS=7',
            'SECRET_KEY=$SECRET_KEY',
            'RESET_PASSWORD_TOKEN_SECRET=$RESET_PASSWORD_TOKEN_SECRET',
            'VERIFICATION_TOKEN_SECRET=$VERIFICATION_TOKEN_SECRET',
            'ALGORITHM=$ALGORITHM',
            'AWS_PAGER=',
            'EOF',
            '',
            '# ============= Clone Project & Build Go Binaries =============',
            'cd /home/ec2-user',
            'git clone https://github.com/ChengTingChiang/ticketing_system.git app || true',
            'cd /home/ec2-user/app',
            '',
            '# Install Python dependencies',
            '/root/.local/bin/uv sync --frozen --no-dev || true',
            '',
            '# Build Go loadtest binaries',
            'cd /home/ec2-user/app/script/go_client',
            'export PATH=/usr/local/go/bin:$PATH',
            f'CGO_ENABLED=0 GOOS=linux GOARCH={go_arch} go build -ldflags="-w -s" -o reserved_loadtest reserved_loadtest.go types.go',
            f'CGO_ENABLED=0 GOOS=linux GOARCH={go_arch} go build -ldflags="-w -s" -o concurrent_loadtest concurrent_loadtest.go types.go',
            f'CGO_ENABLED=0 GOOS=linux GOARCH={go_arch} go build -ldflags="-w -s" -tags full_reserved -o full_reserved_loadtest full_reserved_loadtest.go types.go',
            'chmod +x reserved_loadtest concurrent_loadtest full_reserved_loadtest',
            '',
            '# Create symlink for seating config',
            'ln -sf /home/ec2-user/app/script/seating_config.json /home/ec2-user/app/script/go_client/seating_config.json',
            '',
            '# Fix ownership',
            'chown -R ec2-user:ec2-user /home/ec2-user',
            '',
            '# ============= Create Helper Scripts =============',
            "cat > /home/ec2-user/run-loadtest.sh << 'SCRIPT'",
            '#!/bin/bash',
            'source /etc/profile.d/go.sh',
            'source /home/ec2-user/.env',
            'cd /home/ec2-user/app/script/go_client',
            'exec "$@"',
            'SCRIPT',
            'chmod +x /home/ec2-user/run-loadtest.sh',
            '',
            "cat > /home/ec2-user/update-app.sh << 'SCRIPT'",
            '#!/bin/bash',
            'cd /home/ec2-user/app',
            'git pull origin main',
            'cd script/go_client',
            'source /etc/profile.d/go.sh',
            'go build -ldflags="-w -s" -o reserved_loadtest reserved_loadtest.go types.go',
            'go build -ldflags="-w -s" -o concurrent_loadtest concurrent_loadtest.go types.go',
            'go build -ldflags="-w -s" -tags full_reserved -o full_reserved_loadtest full_reserved_loadtest.go types.go',
            'echo "App updated and rebuilt!"',
            'SCRIPT',
            'chmod +x /home/ec2-user/update-app.sh',
            '',
            'chown ec2-user:ec2-user /home/ec2-user/*.sh',
            '',
            'echo "============================================"',
            'echo "LoadTest EC2 instance ready!"',
            'echo "Go: $(go version)"',
            'echo "k6: $(k6 version)"',
            'echo "Run: cd ~/app/script/go_client && ./reserved_loadtest"',
            'echo "============================================"',
        )

        return user_data
