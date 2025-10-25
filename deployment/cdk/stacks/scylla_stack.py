"""
ScyllaDB EC2 Cluster Stack for Ticketing System

Architecture:
- 3-node ScyllaDB cluster (or 1-node for development)
- EC2 instances with native ScyllaDB installation (no Docker overhead)
- i3.xlarge instances (4 vCPU, 30.5 GB RAM, 950 GB NVMe SSD)
- NetworkTopologyStrategy with RF=3 for high availability

Performance:
- Each node: 4 vCPU (4 shards per node)
- Total: 12 shards across cluster
- Expected throughput: 100,000+ ops/sec per node
- Low-latency: sub-millisecond p99 with proper tuning

Cost (3-node cluster in us-west-2):
- 3 × i3.xlarge On-Demand: ~$0.312/hour × 3 × 730 hours = ~$683/month
- 3 × i3.xlarge Spot (70% savings): ~$205/month
- Development (1-node): ~$228/month (On-Demand) or ~$68/month (Spot)

See also: SCYLLA_SPEC.md for configuration details
"""

from pathlib import Path

from aws_cdk import CfnOutput, Stack, Tags, aws_ec2 as ec2, aws_iam as iam
from constructs import Construct


class ScyllaStack(Stack):
    """
    ScyllaDB cluster on EC2 instances with native installation

    Configuration (production 3-node cluster):
    - Instance type: i3.xlarge (4 vCPU, 30.5 GB RAM, 950 GB NVMe SSD)
    - Node count: 3 (minimum for RF=3)
    - Replication factor: 3 (high availability)
    - Consistency level: LOCAL_QUORUM (strong consistency)

    Development (single-node):
    - Instance type: t3.xlarge (4 vCPU, 16 GB RAM, EBS storage)
    - Node count: 1
    - Replication factor: 1
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc | None = None,
        node_count: int = 3,
        instance_type: str = 'i3.xlarge',
        use_spot_instances: bool = False,
        environment: str = 'production',
        **kwargs,
    ) -> None:
        """
        Initialize ScyllaDB Stack

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: Optional VPC for ScyllaDB deployment. If not provided, creates a new VPC.
            node_count: Number of ScyllaDB nodes (default: 3, min: 1)
            instance_type: EC2 instance type (default: i3.xlarge)
            use_spot_instances: Use Spot instances for cost savings (default: False)
            environment: Deployment environment (production|staging|development)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Validate node count
        if node_count < 1:
            raise ValueError('node_count must be at least 1')
        if node_count == 2:
            raise ValueError('node_count of 2 is not recommended (use 1 or 3+)')

        # ============= VPC =============
        # Create VPC if not provided (ScyllaDB as first infrastructure component)
        if vpc is None:
            vpc = ec2.Vpc(
                self,
                'TicketingVpc',
                max_azs=3,  # Use 3 availability zones for high availability
                nat_gateways=1,  # NAT Gateway for private subnets (cost: ~$32/month)
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
                ],
            )

        self.vpc = vpc

        # ============= Security Group =============
        self.scylla_security_group = ec2.SecurityGroup(
            self,
            'ScyllaSecurityGroup',
            vpc=vpc,
            description='Security group for ScyllaDB cluster',
            allow_all_outbound=True,
        )

        # CQL native protocol (client connections)
        self.scylla_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9042),
            description='CQL native protocol',
        )

        # Inter-node communication (gossip protocol)
        self.scylla_security_group.add_ingress_rule(
            peer=self.scylla_security_group,
            connection=ec2.Port.tcp(7000),
            description='Inter-node communication',
        )

        # Inter-node communication (SSL)
        self.scylla_security_group.add_ingress_rule(
            peer=self.scylla_security_group,
            connection=ec2.Port.tcp(7001),
            description='Inter-node communication (SSL)',
        )

        # JMX monitoring
        self.scylla_security_group.add_ingress_rule(
            peer=self.scylla_security_group,
            connection=ec2.Port.tcp(7199),
            description='JMX monitoring',
        )

        # REST API
        self.scylla_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(10000),
            description='REST API',
        )

        # Prometheus metrics
        self.scylla_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9180),
            description='Prometheus metrics',
        )

        # SSH access (for administration)
        self.scylla_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(22),
            description='SSH access',
        )

        # ============= IAM Role =============
        # IAM role for ScyllaDB instances (for CloudWatch, SSM, etc.)
        scylla_role = iam.Role(
            self,
            'ScyllaInstanceRole',
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=[
                # SSM for remote access (no need for SSH keys)
                iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
                # CloudWatch for logs and metrics
                iam.ManagedPolicy.from_aws_managed_policy_name('CloudWatchAgentServerPolicy'),
            ],
        )

        # ============= User Data Script =============
        # Load initialization script from file
        script_path = Path(__file__).parent.parent / 'static' / 'scylla_userdata.sh'
        with open(script_path) as f:
            user_data_script = f.read()

        # Replace placeholders
        user_data_script = user_data_script.replace('{{NODE_COUNT}}', str(node_count))
        user_data_script = user_data_script.replace('{{ENVIRONMENT}}', environment)

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(user_data_script)

        # ============= AMI Selection =============
        # Use Amazon Linux 2023 (AL2023) as base OS
        # ScyllaDB will be installed via user data script
        ami = ec2.MachineImage.latest_amazon_linux2023(
            edition=ec2.AmazonLinuxEdition.STANDARD,
            cpu_type=ec2.AmazonLinuxCpuType.X86_64,
        )

        # ============= Launch Template =============
        ec2.LaunchTemplate(
            self,
            'ScyllaLaunchTemplate',
            instance_type=ec2.InstanceType(instance_type),
            machine_image=ami,
            security_group=self.scylla_security_group,
            role=scylla_role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name='/dev/xvda',
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=100,  # 100 GB root volume
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                ),
            ],
            # Enable detailed monitoring for better observability
            detailed_monitoring=True,
        )

        # ============= EC2 Instances =============
        # Deploy instances across multiple AZs for high availability
        azs = vpc.availability_zones[:node_count]
        self.instances = []
        seed_node_ips = []

        for i in range(node_count):
            # Select subnet based on AZ
            subnet_selection = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                availability_zones=[azs[i % len(azs)]],
            )

            # Create instance
            instance = ec2.Instance(
                self,
                f'ScyllaNode{i + 1}',
                instance_type=ec2.InstanceType(instance_type),
                machine_image=ami,
                vpc=vpc,
                vpc_subnets=subnet_selection,
                security_group=self.scylla_security_group,
                role=scylla_role,
                user_data=user_data,
                block_devices=[
                    ec2.BlockDevice(
                        device_name='/dev/xvda',
                        volume=ec2.BlockDeviceVolume.ebs(
                            volume_size=100,
                            volume_type=ec2.EbsDeviceVolumeType.GP3,
                            encrypted=True,
                            delete_on_termination=True,
                        ),
                    ),
                ],
            )

            # Add tags
            Tags.of(instance).add('Name', f'scylla-node-{i + 1}')
            Tags.of(instance).add('ScyllaCluster', construct_id)
            Tags.of(instance).add('ScyllaNodeIndex', str(i))
            Tags.of(instance).add('Environment', environment)

            self.instances.append(instance)

            # First node is the seed node
            if i == 0:
                seed_node_ips.append(instance.instance_private_ip)
                Tags.of(instance).add('ScyllaSeedNode', 'true')

        # ============= Outputs =============
        CfnOutput(
            self,
            'VpcId',
            value=vpc.vpc_id,
            description='VPC ID for other stacks to reference',
        )

        CfnOutput(
            self,
            'ClusterSize',
            value=str(node_count),
            description='Number of ScyllaDB nodes in cluster',
        )

        CfnOutput(
            self,
            'InstanceType',
            value=instance_type,
            description='EC2 instance type for ScyllaDB nodes',
        )

        # Output private IPs of all nodes
        for i, instance in enumerate(self.instances):
            CfnOutput(
                self,
                f'Node{i + 1}PrivateIP',
                value=instance.instance_private_ip,
                description=f'Private IP of ScyllaDB node {i + 1}',
            )

        # Connection string for application
        contact_points = [inst.instance_private_ip for inst in self.instances]
        CfnOutput(
            self,
            'ContactPoints',
            value=f'["{'", "'.join(contact_points)}"]',
            description='ScyllaDB contact points (JSON array format)',
        )

        CfnOutput(
            self,
            'CQLPort',
            value='9042',
            description='CQL native protocol port',
        )

        # SSH instructions
        CfnOutput(
            self,
            'SSHInstructions',
            value=f'aws ssm start-session --target {self.instances[0].instance_id}',
            description='Connect to ScyllaDB node via AWS Systems Manager Session Manager',
        )

        # Store references
        self.security_group = self.scylla_security_group
        self.seed_node = self.instances[0]
        self.contact_points = contact_points
