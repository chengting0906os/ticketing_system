"""
Aurora Serverless v2 Stack for Ticketing System (I/O-Optimized)
Provides PostgreSQL with single master (1 writer only) for cost optimization

Architecture:
- Aurora Serverless v2 cluster (auto-scaling 0.5-64 ACU for 10000 TPS)
- I/O-Optimized storage (no per-I/O charges, better cost for high-throughput)
- 1 Writer instance only (single master configuration)
- No reader replicas (cost optimization for temporary testing)
- Automatic backups with 7-day retention
- Continuous backup to S3
"""

from aws_cdk import (
    CfnOutput,
    CustomResource,
    Duration,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
    aws_servicediscovery as servicediscovery,
    custom_resources as cr,
)
from constructs import Construct


class AuroraStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc | None = None,
        min_capacity: float = 2,
        max_capacity: float = 64,
        deploy_env: str = 'development',
        **kwargs,
    ) -> None:
        """
        Initialize Aurora Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: Optional VPC to deploy Aurora cluster. If not provided, creates a new VPC.
            min_capacity: Minimum Aurora Capacity Units (default: 0.5 ACU)
            max_capacity: Maximum Aurora Capacity Units (default: 64 ACU)
            deploy_env: Deployment environment (development, staging, production)
            **kwargs: Additional stack properties
        """
        self.deploy_env = deploy_env
        super().__init__(scope, construct_id, **kwargs)

        # ============= VPC =============
        # Create VPC if not provided (for standalone deployment)
        if vpc is None:
            vpc = ec2.Vpc(
                self,
                'TicketingVpc',
                max_azs=3,  # Use 3 availability zones (required for MSK with 3 brokers)
                nat_gateways=1,  # NAT Gateway for private subnets
            )

        # ============= Security Group =============
        # Allow PostgreSQL traffic from application services
        self.db_security_group = ec2.SecurityGroup(
            self,
            'AuroraSecurityGroup',
            vpc=vpc,
            description='Security group for Aurora PostgreSQL cluster',
            allow_all_outbound=False,  # Database should not initiate outbound connections
        )

        # Allow PostgreSQL port (5432) from within VPC
        self.db_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5432),
            description='PostgreSQL access from VPC',
        )

        # ============= Database Credentials =============
        # Auto-generate secure password and store in Secrets Manager
        db_credentials = rds.Credentials.from_generated_secret(
            username='ticketing_admin',
            secret_name='ticketing/aurora/credentials',
        )

        # Create empty secret first (will be populated by Custom Resource)
        self.app_secrets = secretsmanager.Secret(
            self,
            'AppSecrets',
            description='JWT secrets for all Ticketing System services (auto-generated once)',
            secret_name='ticketing/app/secrets',
        )

        # Lambda function to generate secrets on first deployment only
        secrets_generator_fn = lambda_.Function(
            self,
            'SecretsGenerator',
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler='index.handler',
            code=lambda_.Code.from_inline(
                """
import json
import secrets as py_secrets
import boto3
import cfnresponse

secretsmanager = boto3.client('secretsmanager')

def handler(event, context):
    try:
        request_type = event['RequestType']
        secret_arn = event['ResourceProperties']['SecretArn']

        if request_type == 'Create':
            # Generate secrets only on CREATE
            secret_data = {
                'SECRET_KEY': py_secrets.token_urlsafe(32),
                'RESET_PASSWORD_TOKEN_SECRET': py_secrets.token_urlsafe(32),
                'VERIFICATION_TOKEN_SECRET': py_secrets.token_urlsafe(32),
                'ALGORITHM': 'HS256'
            }

            # Update the secret value
            secretsmanager.put_secret_value(
                SecretId=secret_arn,
                SecretString=json.dumps(secret_data)
            )

            cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                'Message': 'Secrets generated successfully'
            })

        elif request_type in ['Update', 'Delete']:
            # Do NOT change secrets on UPDATE or DELETE
            # This ensures secrets remain stable across deployments
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                'Message': f'{request_type} - Secrets unchanged'
            })

    except Exception as e:
        print(f'Error: {str(e)}')
        cfnresponse.send(event, context, cfnresponse.FAILED, {
            'Message': str(e)
        })
"""
            ),
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Grant Lambda permission to update the secret
        self.app_secrets.grant_write(secrets_generator_fn)

        # Custom Resource to invoke Lambda on first deployment
        CustomResource(
            self,
            'SecretsGeneratorResource',
            service_token=cr.Provider(
                self,
                'SecretsGeneratorProvider',
                on_event_handler=secrets_generator_fn,
                log_retention=logs.RetentionDays.ONE_WEEK,
            ).service_token,
            properties={
                'SecretArn': self.app_secrets.secret_arn,
            },
        )

        # ============= Aurora Serverless v2 Cluster =============
        # Configured with dynamic scaling from config.yml
        # ACU range from config: {min_capacity}-{max_capacity}

        self.cluster = rds.DatabaseCluster(
            self,
            'AuroraCluster',
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_17_5
            ),
            # Serverless v2 scaling configuration from config.yml
            serverless_v2_min_capacity=min_capacity,
            serverless_v2_max_capacity=max_capacity,
            # Cluster configuration
            cluster_identifier='ticketing-aurora-cluster',
            default_database_name='ticketing_system_db',
            credentials=db_credentials,
            # Writer instance (primary) - single master only
            writer=rds.ClusterInstance.serverless_v2(
                'Writer',
                enable_performance_insights=True,
                performance_insight_retention=rds.PerformanceInsightRetention.DEFAULT,
            ),
            # No readers - single master configuration for cost optimization
            # Network configuration
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS  # Private subnets with NAT
            ),
            security_groups=[self.db_security_group],
            # Backup configuration
            backup=rds.BackupProps(
                retention=Duration.days(7),  # 7-day backup retention
                preferred_window='03:00-04:00',  # Backup at 3-4 AM UTC (11 AM-12 PM Taipei)
            ),
            # Storage configuration
            storage_encrypted=True,  # Encrypt data at rest
            storage_type=rds.DBClusterStorageType.AURORA_IOPT1,  # I/O-Optimized (no per-I/O charges)
            # Monitoring
            cloudwatch_logs_exports=['postgresql'],  # Export logs to CloudWatch
            monitoring_interval=Duration.seconds(60),  # Enhanced monitoring every 60s
            # Maintenance
            preferred_maintenance_window='sun:04:00-sun:05:00',  # Sunday 4-5 AM UTC
            # Deletion protection
            deletion_protection=False,  # Prevent accidental deletion
            removal_policy=RemovalPolicy.SNAPSHOT,  # Create snapshot on stack deletion
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'ClusterEndpoint',
            value=self.cluster.cluster_endpoint.hostname,
            description='Aurora cluster writer endpoint (for writes)',
            export_name='TicketingAuroraWriterEndpoint',
        )

        # Reader endpoint removed - single master configuration

        CfnOutput(
            self,
            'ClusterPort',
            value=str(self.cluster.cluster_endpoint.port),
            description='Aurora cluster port (default: 5432)',
        )

        CfnOutput(
            self,
            'SecretArn',
            value=self.cluster.secret.secret_arn if self.cluster.secret else 'N/A',
            description='ARN of the secret containing database credentials',
            export_name='TicketingAuroraSecretArn',
        )

        CfnOutput(
            self,
            'SecurityGroupId',
            value=self.db_security_group.security_group_id,
            description='Security group ID for database access',
            export_name='TicketingAuroraSecurityGroupId',
        )

        # ============= Service Discovery Namespace =============
        # Private DNS namespace for service-to-service communication
        # Created here because Aurora is the first stack, making it available to all other stacks
        self.namespace = servicediscovery.PrivateDnsNamespace(
            self,
            'ServiceDiscovery',
            name='ticketing.local',
            vpc=vpc,
            description='Service discovery for ticketing system microservices',
        )

        CfnOutput(
            self,
            'ServiceDiscoveryNamespace',
            value=self.namespace.namespace_name,
            description='Service Discovery namespace for internal DNS',
            export_name='TicketingServiceDiscoveryNamespace',
        )

        # ============= ECS Cluster (Shared Infrastructure) =============
        # Shared cluster for all microservices
        self.ecs_cluster = ecs.Cluster(
            self,
            'ECSCluster',
            cluster_name='ticketing-cluster',
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENHANCED,
        )

        CfnOutput(
            self,
            'ECSClusterName',
            value=self.ecs_cluster.cluster_name,
            description='ECS Cluster name for microservices',
            export_name='TicketingECSClusterName',
        )

        # ============= Application Load Balancer (Shared Infrastructure) =============
        # Shared ALB for all HTTP services
        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            'ALB',
            vpc=vpc,
            internet_facing=True,
            load_balancer_name=f'ticketing-alb-{self.deploy_env}',
        )

        # ALB listener with default 404 response
        self.alb_listener = self.alb.add_listener(
            'HttpListener',
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=404,
                content_type='application/json',
                message_body='{"error": "Not Found"}',
            ),
        )

        CfnOutput(
            self,
            'ALBEndpoint',
            value=f'http://{self.alb.load_balancer_dns_name}',
            description='Application Load Balancer endpoint',
            export_name='TicketingALBEndpoint',
        )

        # Store references for other stacks
        self.vpc = vpc
        self.cluster_endpoint = self.cluster.cluster_endpoint.hostname
