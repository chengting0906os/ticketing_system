"""
EC2 Kafka Stack - Self-hosted Kafka cluster on single EC2 instance
Runs 3 Kafka brokers using Docker Compose with KRaft mode

Architecture:
- 1 × EC2 instance (instance type from config.yml)
- 3 × Kafka brokers in Docker containers (KRaft mode)
- KRaft mode (no ZooKeeper needed)
- Storage: NVMe instance store (m6id) or EBS (configurable)
- Cost: ~$82/month with m6id.large (vs MSK $466/month)

Savings: $384/month (82% reduction)
Benefits: High I/O performance with NVMe, simple deployment, reliable single-host configuration

Configuration values come from deployment/config.yml:
- config['kafka']['instance_type'] (e.g., m6id.large)
- config['kafka']['storage_type'] ('nvme' or 'ebs')
- config['kafka']['storage_gb'] (only for EBS)
"""

from aws_cdk import CfnOutput, Stack, aws_ec2 as ec2
from constructs import Construct


class EC2KafkaStack(Stack):
    """
    Self-hosted Kafka cluster on single EC2 instance

    Configuration from config.yml:
    - Instance: config['kafka']['instance_type'] (e.g., m6id.large)
    - Storage Type: config['kafka']['storage_type'] ('nvme' or 'ebs')
    - Brokers: 3 brokers in Docker containers
    - Network: Private subnet
    - Cost: ~$82/month (m6id.large with NVMe)

    NVMe Configuration (storage_type='nvme'):
    - Uses instance store (m6id.large: 118 GB)
    - High IOPS (~40K)
    - Data lost on stop/start (reboot preserves data)

    EBS Configuration (storage_type='ebs'):
    - Storage: config['kafka']['storage_gb'] (e.g., 50 GB)
    - Data persists across stop/start

    Single instance runs 3 Kafka brokers in Docker,
    providing cost-effective and reliable messaging.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        config: dict,
        **kwargs,
    ) -> None:
        """
        Initialize EC2 Kafka Stack with single instance

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC to deploy EC2 instance
            config: Environment configuration dictionary
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Extract Kafka configuration
        kafka_config = config.get('kafka', {})
        instance_type_str = kafka_config.get('instance_type', 't4g.medium')
        storage_type = kafka_config.get('storage_type', 'ebs')  # 'ebs' or 'nvme'
        storage_gb = kafka_config.get('storage_gb', 50)  # Only used for EBS

        # Determine CPU architecture based on instance type
        # m6id is Intel (x86_64), t4g is ARM
        is_arm = instance_type_str.startswith('t4g') or instance_type_str.startswith('m6g')
        cpu_type = ec2.AmazonLinuxCpuType.ARM_64 if is_arm else ec2.AmazonLinuxCpuType.X86_64

        # ============= Security Group =============
        self.kafka_sg = ec2.SecurityGroup(
            self,
            'KafkaSecurityGroup',
            vpc=vpc,
            description='Security group for EC2 Kafka cluster',
            allow_all_outbound=True,
        )

        # Kafka broker ports (9092, 9093, 9094 for 3 brokers)
        for port in [9092, 9093, 9094]:
            self.kafka_sg.add_ingress_rule(
                peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(port),
                description=f'Kafka broker port {port}',
            )

        # Kafka controller ports (9095, 9096, 9097)
        for port in [9095, 9096, 9097]:
            self.kafka_sg.add_ingress_rule(
                peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(port),
                description=f'Kafka controller port {port}',
            )

        # SSH access
        self.kafka_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(22),
            description='SSH access from VPC',
        )

        # ============= User Data Script =============
        user_data = ec2.UserData.for_linux()

        # Generate mount commands based on storage type
        if storage_type == 'nvme':
            # NVMe instance store - mount before creating Kafka directories
            mount_commands = [
                '# Mount NVMe instance store for Kafka data',
                'DATA_DEVICE="/dev/nvme1n1"',
                '',
                'if [ ! -b "$DATA_DEVICE" ]; then',
                '  echo "ERROR: NVMe instance store $DATA_DEVICE not found"',
                '  exit 1',
                'fi',
                '',
                'echo "Using NVMe instance store: $DATA_DEVICE"',
                '',
                '# Format NVMe (instance store is always empty on first boot)',
                'mkfs.xfs -f "$DATA_DEVICE"',
                '',
                '# Create mount point and mount',
                'mkdir -p /opt/kafka',
                'mount "$DATA_DEVICE" /opt/kafka',
                '',
                '# Note: Do NOT add to fstab - instance store may not exist after stop/start',
            ]
        else:
            # EBS - /opt/kafka will be on root volume
            mount_commands = [
                '# Using EBS root volume for Kafka data',
                'mkdir -p /opt/kafka',
            ]

        user_data.add_commands(
            '#!/bin/bash',
            'set -e',
            '',
            '# Update system',
            'yum update -y',
            '',
            '# Install Docker and docker-compose',
            'yum install -y docker',
            'systemctl start docker',
            'systemctl enable docker',
            '',
            '# Install docker-compose',
            'curl -L "https://github.com/docker/compose/releases/download/v2.23.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose',
            'chmod +x /usr/local/bin/docker-compose',
            '',
            '# Get own IP address',
            "OWN_IP=$(hostname -I | awk '{print $1}')",
            '',
            *mount_commands,
            '',
            '# Create Kafka broker directories with correct permissions',
            'mkdir -p /opt/kafka/{broker1,broker2,broker3}/data',
            'chown -R 1000:1000 /opt/kafka/broker1/data /opt/kafka/broker2/data /opt/kafka/broker3/data',
            '',
            '# Create docker-compose.yml',
            "cat > /opt/kafka/docker-compose.yml << 'EOF'",
            "version: '3.8'",
            '',
            'services:',
            '  kafka-1:',
            '    image: confluentinc/cp-kafka:7.5.0',
            '    container_name: kafka-1',
            '    restart: unless-stopped',
            '    ports:',
            '      - "9092:9092"',
            '      - "9095:9095"',
            '    volumes:',
            '      - ./broker1/data:/var/lib/kafka/data',
            '    environment:',
            '      KAFKA_NODE_ID: 1',
            '      KAFKA_PROCESS_ROLES: broker,controller',
            '      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka-1:9095,2@kafka-2:9096,3@kafka-3:9097',
            '      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9095',
            '      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://${OWN_IP}:9092',
            '      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER',
            '      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT',
            '      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT',
            '      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 3',
            '      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 3',
            '      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 2',
            '      KAFKA_LOG_RETENTION_HOURS: 168',
            '      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"',
            '      CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk',
            '',
            '  kafka-2:',
            '    image: confluentinc/cp-kafka:7.5.0',
            '    container_name: kafka-2',
            '    restart: unless-stopped',
            '    ports:',
            '      - "9093:9093"',
            '      - "9096:9096"',
            '    volumes:',
            '      - ./broker2/data:/var/lib/kafka/data',
            '    environment:',
            '      KAFKA_NODE_ID: 2',
            '      KAFKA_PROCESS_ROLES: broker,controller',
            '      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka-1:9095,2@kafka-2:9096,3@kafka-3:9097',
            '      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9093,CONTROLLER://0.0.0.0:9096',
            '      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://${OWN_IP}:9093',
            '      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER',
            '      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT',
            '      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT',
            '      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 3',
            '      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 3',
            '      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 2',
            '      KAFKA_LOG_RETENTION_HOURS: 168',
            '      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"',
            '      CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk',
            '',
            '  kafka-3:',
            '    image: confluentinc/cp-kafka:7.5.0',
            '    container_name: kafka-3',
            '    restart: unless-stopped',
            '    ports:',
            '      - "9094:9094"',
            '      - "9097:9097"',
            '    volumes:',
            '      - ./broker3/data:/var/lib/kafka/data',
            '    environment:',
            '      KAFKA_NODE_ID: 3',
            '      KAFKA_PROCESS_ROLES: broker,controller',
            '      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka-1:9095,2@kafka-2:9096,3@kafka-3:9097',
            '      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9094,CONTROLLER://0.0.0.0:9097',
            '      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://${OWN_IP}:9094',
            '      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER',
            '      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT',
            '      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT',
            '      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 3',
            '      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 3',
            '      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 2',
            '      KAFKA_LOG_RETENTION_HOURS: 168',
            '      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"',
            '      CLUSTER_ID: MkU3OEVBNTcwNTJENDM2Qk',
            'EOF',
            '',
            '# Replace OWN_IP placeholder',
            r'sed -i "s/\${OWN_IP}/$OWN_IP/g" /opt/kafka/docker-compose.yml',
            '',
            '# Start Kafka cluster',
            'cd /opt/kafka',
            'docker-compose up -d',
            '',
            'echo "Kafka cluster started successfully!"',
        )

        # ============= Create Kafka Instance =============
        private_subnets = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnets

        # Build block devices list based on storage type
        if storage_type == 'nvme':
            # NVMe instance store - only root volume, smaller size
            block_devices = [
                ec2.BlockDevice(
                    device_name='/dev/xvda',
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=20,  # Small root volume (OS + Docker only)
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=True,
                        encrypted=True,
                    ),
                ),
            ]
        else:
            # EBS - larger root volume for Kafka data
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

        self.instance = ec2.Instance(
            self,
            'KafkaInstance',
            instance_type=ec2.InstanceType(instance_type_str),
            machine_image=ec2.MachineImage.latest_amazon_linux2(cpu_type=cpu_type),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[private_subnets[0]]),
            security_group=self.kafka_sg,
            user_data=user_data,
            block_devices=block_devices,
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'KafkaInstanceId',
            value=self.instance.instance_id,
            description='Kafka Instance ID',
        )

        CfnOutput(
            self,
            'KafkaPrivateIP',
            value=self.instance.instance_private_ip,
            description='Kafka Instance Private IP',
        )

        # Bootstrap servers (all 3 brokers on same IP, different ports)
        self.bootstrap_servers = (
            f'{self.instance.instance_private_ip}:9092,'
            f'{self.instance.instance_private_ip}:9093,'
            f'{self.instance.instance_private_ip}:9094'
        )

        CfnOutput(
            self,
            'KafkaBootstrapServers',
            value=self.bootstrap_servers,
            description='Kafka Bootstrap Servers (internal)',
            export_name='TicketingKafkaBootstrapServers',
        )
