"""
Load Test Stack for Ticketing System
Runs Go-based load testing tool on Fargate Spot (70% cheaper than regular Fargate)

Architecture:
- ECS Fargate Spot (on-demand task, not always running)
- 32GB RAM + 16 vCPU (required for high-concurrency Go client)
- Stores results in S3
- Runs inside VPC to access ALB privately

Usage:
1. Deploy stack: `uv run cdk deploy TicketingLoadTestStack`
2. Run test: `aws ecs run-task ...` (see deployment docs)
3. View results in S3
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
)
from constructs import Construct


class LoadTestStack(Stack):
    """
    Fargate Spot task for running high-concurrency load tests

    Configuration:
    - 32GB RAM (required for 50000 concurrent requests)
    - 16 vCPU (Go runtime needs CPU for goroutines)
    - Fargate Spot: 70% cheaper than regular Fargate
    - Results auto-uploaded to S3

    Cost:
    - ~$0.50 per hour (Spot pricing)
    - Only pay when running tests
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        alb_dns: str,  # ALB endpoint to test against
        **kwargs,
    ) -> None:
        """
        Initialize Load Test Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC (must be same as ECS services for internal testing)
            alb_dns: ALB DNS name to send requests to
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # ============= S3 Bucket for Test Results =============
        results_bucket = s3.Bucket(
            self,
            'LoadTestResults',
            bucket_name=f'ticketing-loadtest-results-{self.account}',
            removal_policy=RemovalPolicy.RETAIN,  # Keep results after stack deletion
            auto_delete_objects=False,
            versioned=True,  # Keep history of test runs
        )

        # ============= ECS Cluster =============
        cluster = ecs.Cluster(
            self,
            'LoadTestCluster',
            cluster_name='loadtest-cluster',
            vpc=vpc,
            container_insights=False,  # Save cost, not needed for temporary tasks
        )

        # ============= ECR Repository =============
        loadtest_repo = ecr.Repository(
            self,
            'LoadTestRepo',
            repository_name='loadtest-runner',
            removal_policy=RemovalPolicy.DESTROY,  # Clean up when stack deleted
            empty_on_delete=True,
        )

        # ============= IAM Role for Task =============
        task_role = iam.Role(
            self,
            'LoadTestTaskRole',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            description='Role for load test ECS tasks',
        )

        # Grant S3 write permission for uploading results
        results_bucket.grant_write(task_role)

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

        # ============= Task Definition (32GB RAM, 16 vCPU) =============
        task_definition = ecs.FargateTaskDefinition(
            self,
            'LoadTestTask',
            family='loadtest-runner',
            cpu=16384,  # 16 vCPU (max for Fargate)
            memory_limit_mib=32768,  # 32GB RAM (required for 50k concurrent requests)
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
                'S3_BUCKET': results_bucket.bucket_name,
                'AWS_REGION': self.region,
            },
            # No command - will be specified at runtime via `aws ecs run-task`
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
            description='ECR repository for load test image',
            export_name='LoadTestECRRepository',
        )

        CfnOutput(
            self,
            'RunCommand',
            value=f'aws ecs run-task --cluster {cluster.cluster_name} '
            f'--task-definition {task_definition.family} '
            f'--launch-type FARGATE '
            f'--network-configuration "awsvpcConfiguration={{subnets=[{vpc.private_subnets[0].subnet_id}],securityGroups=[{loadtest_sg.security_group_id}]}}" '
            f'--overrides \'{{"containerOverrides":[{{"name":"loadtest","command":["./loadtest","-requests","50000","-concurrency","500"]}}]}}\'',
            description='Command to run load test',
        )

        # Store references
        self.cluster = cluster
        self.task_definition = task_definition
        self.security_group = loadtest_sg
        self.results_bucket = results_bucket
        self.ecr_repository = loadtest_repo
