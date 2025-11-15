"""
Load Test Stack for Ticketing System
Runs load testing using loadtest-service image (Go binaries) on Fargate

Architecture:
- ECS Fargate task (on-demand, not always running)
- Uses loadtest-service ECR image (Alpine + Go binaries: reserved_loadtest, concurrent_loadtest, full_reserved_loadtest)
- ECS Exec enabled for interactive shell access
- Stores results in S3
- Runs inside VPC to access ALB/Aurora/Kvrocks/Kafka
- Configurable CPU/RAM from config.yml (up to 16 vCPU + 120 GB)

Usage:
1. Deploy stack: `uv run cdk deploy TicketingLoadTestStack`
2. Run task: `make aws-loadtest-run` (starts task with sleep infinity)
3. Exec into task: `make aws-loadtest-exec` (interactive shell)
4. Run loadtest: Inside task, cd script/go_client && make frlt WORKERS=500 BATCH=1
5. Stop task: `make aws-loadtest-stop`

Cost:
- 16 vCPU + 32 GB: ~$0.60/hour (only when running)
- Run for 10 min: ~$0.10
- Much cheaper than running EC2 24/7
"""

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
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
        ecs_cluster: ecs.ICluster,  # Use shared cluster
        alb_dns: str,  # ALB endpoint to test against (internal DNS)
        aurora_cluster_endpoint: str,  # Aurora endpoint for seed operations
        aurora_cluster_secret: secretsmanager.ISecret,  # Aurora credentials
        app_secrets: secretsmanager.ISecret,  # JWT secrets
        kafka_bootstrap_servers: str,  # Kafka endpoints
        kvrocks_endpoint: str,  # Kvrocks endpoint (host:port)
        config: dict,  # Configuration from config.yml
        **kwargs,
    ) -> None:
        """
        Initialize Load Test Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC (must be same as ECS services for internal testing)
            ecs_cluster: Shared ECS cluster from Aurora Stack
            alb_dns: ALB internal DNS name (saves data transfer cost)
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
        task_cpu = loadtest_config.get('task_cpu', 2048)  # Default: 2 vCPU
        task_memory = loadtest_config.get('task_memory', 4096)  # Default: 4GB

        # Parse Kvrocks endpoint
        kvrocks_host, kvrocks_port = kvrocks_endpoint.split(':')

        # ============= S3 Bucket for Test Results =============
        results_bucket = s3.Bucket(
            self,
            'LoadTestResults',
            bucket_name=f'ticketing-loadtest-results-{self.account}',
            removal_policy=RemovalPolicy.RETAIN,  # Keep results after stack deletion
            auto_delete_objects=False,
            versioned=True,  # Keep history of test runs
        )

        # Use shared cluster (no need to create new one)
        cluster = ecs_cluster

        # ============= ECR Repository (use loadtest image) =============
        # Use dedicated loadtest image with Go binaries and Python tools
        loadtest_repo = ecr.Repository.from_repository_name(
            self, 'LoadTestServiceRepo', repository_name='loadtest-service'
        )

        # ============= IAM Roles =============
        execution_role = iam.Role(
            self,
            'LoadTestExecutionRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    'service-role/AmazonECSTaskExecutionRolePolicy'
                )
            ],
        )

        # Grant access to Aurora and App secrets
        aurora_cluster_secret.grant_read(execution_role)
        app_secrets.grant_read(execution_role)

        task_role = iam.Role(
            self,
            'LoadTestTaskRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            description='Role for load test ECS tasks',
        )

        # Grant S3 write permission for uploading results
        results_bucket.grant_write(task_role)

        # Grant SSM permissions for ECS Exec
        task_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore')
        )

        # Grant permissions for running AWS operations inside LoadTest container
        # (needed for make aws-seed, make aws-migrate, make aws-kvrocks-keys, etc.)
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    'ec2:DescribeSubnets',
                    'ec2:DescribeSecurityGroups',
                    'ecs:DescribeServices',
                    'ecs:DescribeTaskDefinition',
                    'ecs:RunTask',
                    'ecs:ListTasks',
                    'ecs:DescribeTasks',
                    # Auto Scaling permissions for finding Kvrocks/Kafka instances
                    'autoscaling:DescribeAutoScalingGroups',
                    # SSM permissions for remote command execution
                    'ssm:SendCommand',
                    'ssm:GetCommandInvocation',
                ],
                resources=['*'],
                effect=iam.Effect.ALLOW,
            )
        )

        # Grant permission to pass ECS task execution role (required for ecs:RunTask)
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=['iam:PassRole'],
                resources=[f'arn:aws:iam::{self.account}:role/*'],
                conditions={'StringLike': {'iam:PassedToService': 'ecs-tasks.amazonaws.com'}},
                effect=iam.Effect.ALLOW,
            )
        )

        # ============= Task Definition (from config.yml) =============
        task_definition = ecs.FargateTaskDefinition(
            self,
            'LoadTestTask',
            family='loadtest-runner',
            cpu=task_cpu,  # From config.yml (dev: 8 vCPU, prod: 16 vCPU)
            memory_limit_mib=task_memory,  # From config.yml (dev: 16GB, prod: 32GB)
            task_role=task_role,
            execution_role=execution_role,
        )

        # CloudWatch Log Group
        log_group = logs.LogGroup(
            self,
            'LoadTestLogs',
            log_group_name='/ecs/loadtest-runner',
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Container Definition
        _ = task_definition.add_container(
            'LoadTestContainer',
            container_name='loadtest',
            image=ecs.ContainerImage.from_ecr_repository(loadtest_repo, tag='latest'),
            logging=ecs.LogDriver.aws_logs(stream_prefix='loadtest', log_group=log_group),
            environment={
                'ALB_HOST': f'http://{alb_dns}',
                'API_HOST': f'http://{alb_dns}',  # For Go loadtest binaries
                'S3_BUCKET': results_bucket.bucket_name,
                'AWS_REGION': self.region,
                # Database configuration (split format for Settings class)
                'POSTGRES_SERVER': aurora_cluster_endpoint,
                'POSTGRES_DB': 'ticketing_system_db',
                'POSTGRES_PORT': '5432',
                # Kafka configuration
                'KAFKA_BOOTSTRAP_SERVERS': kafka_bootstrap_servers,
                # Kvrocks configuration
                'KVROCKS_HOST': kvrocks_host,
                'KVROCKS_PORT': kvrocks_port,
                # Application configuration
                'DEBUG': str(config.get('debug', False)).lower(),
                'DEPLOY_ENV': config.get('environment', 'development'),
                # JWT configuration (required by core_setting.py)
                'ACCESS_TOKEN_EXPIRE_MINUTES': '30',
                'REFRESH_TOKEN_EXPIRE_DAYS': '7',
                # Disable AWS CLI pager (less is not installed in container)
                'AWS_PAGER': '',
            },
            secrets={
                # Aurora credentials (must match Settings field names)
                'POSTGRES_USER': ecs.Secret.from_secrets_manager(aurora_cluster_secret, 'username'),
                'POSTGRES_PASSWORD': ecs.Secret.from_secrets_manager(
                    aurora_cluster_secret, 'password'
                ),
                # App secrets (matching API service configuration)
                'SECRET_KEY': ecs.Secret.from_secrets_manager(app_secrets, 'SECRET_KEY'),
                'RESET_PASSWORD_TOKEN_SECRET': ecs.Secret.from_secrets_manager(
                    app_secrets, 'RESET_PASSWORD_TOKEN_SECRET'
                ),
                'VERIFICATION_TOKEN_SECRET': ecs.Secret.from_secrets_manager(
                    app_secrets, 'VERIFICATION_TOKEN_SECRET'
                ),
                'ALGORITHM': ecs.Secret.from_secrets_manager(app_secrets, 'ALGORITHM'),
            },
            # Command will be overridden at runtime
            # Default: sleep infinity (for ECS Exec)
            command=['sleep', 'infinity'],
        )

        # ============= Security Group =============
        loadtest_sg = ec2.SecurityGroup(
            self,
            'LoadTestSG',
            vpc=vpc,
            description='Security group for load test tasks',
            allow_all_outbound=True,  # Need to call ALB and S3
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'TaskDefinitionArn',
            value=task_definition.task_definition_arn,
            description='Task definition ARN for running load tests',
            export_name='LoadTestTaskDefinitionArn',
        )

        CfnOutput(
            self,
            'ClusterName',
            value=cluster.cluster_name,
            description='ECS cluster name',
            export_name='LoadTestClusterName',
        )

        CfnOutput(
            self,
            'ResultsBucket',
            value=results_bucket.bucket_name,
            description='S3 bucket for test results',
            export_name='LoadTestResultsBucket',
        )

        CfnOutput(
            self,
            'ECRRepository',
            value=loadtest_repo.repository_uri,
            description='ECR repository (ticketing-service)',
            export_name='LoadTestECRRepository',
        )

        CfnOutput(
            self,
            'SecurityGroupId',
            value=loadtest_sg.security_group_id,
            description='Security Group ID for loadtest tasks',
            export_name='LoadTestSecurityGroupId',
        )

        # Store references
        self.cluster = cluster
        self.task_definition = task_definition
        self.security_group = loadtest_sg
        self.results_bucket = results_bucket
        self.ecr_repository = loadtest_repo
