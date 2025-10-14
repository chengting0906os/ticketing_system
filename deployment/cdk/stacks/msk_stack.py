"""
Amazon MSK (Managed Streaming for Apache Kafka) Stack
Provides managed Kafka cluster for event-driven messaging in production

Architecture:
- 3-node Kafka cluster (matches docker-compose setup)
- Multi-AZ deployment for high availability
- VPC integration with database and application stacks
- Security groups for controlled access
"""

from aws_cdk import CfnOutput, Stack, aws_ec2 as ec2, aws_msk as msk
from constructs import Construct


class MSKStack(Stack):
    """
    Amazon MSK Stack for production Kafka infrastructure

    Configuration:
    - Kafka version: 3.5.1 (compatible with Confluent 7.5.0 used in docker-compose)
    - Cluster size: 3 brokers (kafka.m5.large)
    - Storage: 100GB EBS per broker
    - Replication factor: 3 (matches KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR)
    - Security: TLS encryption, IAM authentication

    See also: spec/KAFKA_SPEC.md for topic naming and partition strategy
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
        Initialize MSK Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC to deploy MSK cluster (shared with database and services)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # ============= Security Group =============
        # Allow Kafka traffic from application services
        self.security_group = ec2.SecurityGroup(
            self,
            'MSKSecurityGroup',
            vpc=vpc,
            description='Security group for MSK cluster',
            allow_all_outbound=True,
        )

        # Kafka broker ports
        # 9092: PLAINTEXT (internal communication)
        # 9094: TLS (encrypted client connections)
        # 9098: IAM authentication
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9092),
            description='Kafka PLAINTEXT port',
        )
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9094),
            description='Kafka TLS port',
        )
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9098),
            description='Kafka IAM auth port',
        )

        # ============= MSK Configuration =============
        # Custom Kafka server properties
        # Matches docker-compose settings for consistency
        msk_configuration = msk.CfnConfiguration(
            self,
            'MSKConfiguration',
            name='ticketing-system-kafka-config',
            server_properties="""
# Replication settings (matches docker-compose)
default.replication.factor=3
min.insync.replicas=2
offsets.topic.replication.factor=3
transaction.state.log.replication.factor=3
transaction.state.log.min.isr=2

# Performance tuning
num.network.threads=8
num.io.threads=16
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400
socket.request.max.bytes=104857600

# Log settings
log.retention.hours=168
log.segment.bytes=1073741824
log.retention.check.interval.ms=300000

# Topic settings
auto.create.topics.enable=true
delete.topic.enable=true
""",
        )

        # ============= MSK Cluster =============
        # TODO(human): Choose ONE cluster type (cannot coexist - different bootstrap servers)
        # Set cluster_type to either 'PROVISIONED' or 'SERVERLESS'
        cluster_type = 'PROVISIONED'  # Change to 'SERVERLESS' if needed

        if cluster_type == 'PROVISIONED':
            # Option 1: Provisioned Cluster
            # Best for: Predictable workloads, consistent throughput, cost control
            # Cost: ~$300-500/month for kafka.m5.large × 3
            provisioned_cluster = msk.CfnCluster(
                self,
                'MSKCluster',
                cluster_name='ticketing-system-kafka',
                kafka_version='3.5.1',
                number_of_broker_nodes=3,
                broker_node_group_info=msk.CfnCluster.BrokerNodeGroupInfoProperty(
                    instance_type='kafka.m5.large',
                    client_subnets=[subnet.subnet_id for subnet in vpc.private_subnets],
                    security_groups=[self.security_group.security_group_id],
                    storage_info=msk.CfnCluster.StorageInfoProperty(
                        ebs_storage_info=msk.CfnCluster.EBSStorageInfoProperty(
                            volume_size=100,  # 100 GB per broker
                            provisioned_throughput=msk.CfnCluster.ProvisionedThroughputProperty(
                                enabled=False  # Disable for cost savings
                            ),
                        )
                    ),
                ),
                encryption_info=msk.CfnCluster.EncryptionInfoProperty(
                    encryption_in_transit=msk.CfnCluster.EncryptionInTransitProperty(
                        client_broker='TLS',  # Encrypt client-broker communication
                        in_cluster=True,  # Encrypt inter-broker communication
                    )
                ),
                client_authentication=msk.CfnCluster.ClientAuthenticationProperty(
                    sasl=msk.CfnCluster.SaslProperty(
                        iam=msk.CfnCluster.IamProperty(enabled=True)  # Enable IAM auth
                    )
                ),
                configuration_info=msk.CfnCluster.ConfigurationInfoProperty(
                    arn=msk_configuration.attr_arn, revision=1
                ),
                enhanced_monitoring='PER_TOPIC_PER_BROKER',  # CloudWatch metrics
            )

            # Store cluster reference and extract outputs
            self.cluster = provisioned_cluster
            # Use GetAtt to retrieve bootstrap brokers at deployment time
            bootstrap_tls = provisioned_cluster.get_att('BootstrapBrokerStringTls').to_string()
            bootstrap_iam = provisioned_cluster.get_att('BootstrapBrokerStringSaslIam').to_string()
            cluster_arn = provisioned_cluster.attr_arn

        elif cluster_type == 'SERVERLESS':
            # Option 2: Serverless Cluster
            # Best for: Spiky workloads, auto-scaling, no capacity planning
            # Cost: Pay-per-use (can be higher under sustained load)
            serverless_cluster = msk.CfnServerlessCluster(
                self,
                'MSKServerlessCluster',
                cluster_name='ticketing-system-kafka-serverless',
                client_authentication=msk.CfnServerlessCluster.ClientAuthenticationProperty(
                    sasl=msk.CfnServerlessCluster.SaslProperty(
                        iam=msk.CfnServerlessCluster.IamProperty(enabled=True)
                    )
                ),
                vpc_configs=[
                    msk.CfnServerlessCluster.VpcConfigProperty(
                        subnet_ids=[subnet.subnet_id for subnet in vpc.private_subnets],
                        security_groups=[self.security_group.security_group_id],
                    )
                ],
            )

            # Store cluster reference and extract outputs
            self.cluster = serverless_cluster  # type: ignore[assignment]
            # Serverless cluster uses IAM authentication only
            bootstrap_iam = serverless_cluster.get_att('BootstrapBrokers').to_string()
            bootstrap_tls = 'N/A (Serverless uses IAM authentication only)'
            cluster_arn = serverless_cluster.attr_arn

        else:
            raise ValueError(
                f"Invalid cluster_type: {cluster_type}. Must be 'PROVISIONED' or 'SERVERLESS'"
            )

        # ============= Outputs =============
        CfnOutput(
            self,
            'MSKClusterArn',
            value=cluster_arn,
            description='ARN of the MSK cluster',
            export_name='TicketingSystemMSKClusterArn',
        )

        CfnOutput(
            self,
            'MSKBootstrapBrokers',
            value=bootstrap_tls,
            description='Bootstrap brokers for TLS connections (port 9094, Provisioned only)',
            export_name='TicketingSystemMSKBootstrapBrokersTLS',
        )

        CfnOutput(
            self,
            'MSKBootstrapBrokersIAM',
            value=bootstrap_iam,
            description='Bootstrap brokers for IAM authentication (port 9098)',
            export_name='TicketingSystemMSKBootstrapBrokersIAM',
        )

        CfnOutput(
            self,
            'MSKSecurityGroupId',
            value=self.security_group.security_group_id,
            description='Security group ID for MSK cluster',
            export_name='TicketingSystemMSKSecurityGroupId',
        )
