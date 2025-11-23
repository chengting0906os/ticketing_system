"""
EC2 Kafka Stack - Self-hosted Kafka cluster on 3 EC2 instances
Runs 3 Kafka brokers across 3 Availability Zones with KRaft mode (Native Installation)

Architecture:
- 3 × EC2 instances (one per AZ for high availability)
- 1 Kafka broker per instance (Native Kafka 4.1.1, KRaft mode)
- No ZooKeeper needed (KRaft consensus)
- No Docker - runs natively with Java 17 (Amazon Corretto)
- Storage: EBS gp3 (configurable size)
- SSM Parameter Store for automatic broker discovery
- Cost: ~$156/month with 3 × c7g.large (ARM Graviton)

Benefits:
- True high availability (tolerates 1 AZ failure)
- Native installation (no Docker overhead)
- ARM Graviton support for 20% cost savings
- Independent scaling and maintenance per broker
- Auto-discovery via SSM Parameter Store (no manual IP configuration)

Configuration values come from deployment/config.yml:
- config['kafka']['instance_type'] (e.g., c7g.large for ARM, c7i.large for x86)
- config['kafka']['instance_count'] (default: 3)
- config['kafka']['storage_type'] ('ebs' or 'nvme')
- config['kafka']['storage_gb'] (EBS volume size per broker)
"""

from aws_cdk import CfnOutput, Fn, Stack, aws_ec2 as ec2, aws_iam as iam, aws_ssm as ssm
from constructs import Construct


class EC2KafkaStack(Stack):
    """
    Self-hosted Kafka cluster on 3 EC2 instances across 3 AZs

    Configuration from config.yml:
    - Instance: config['kafka']['instance_type'] (e.g., c7i.large)
    - Count: config['kafka']['instance_count'] (default: 3)
    - Storage: config['kafka']['storage_gb'] (e.g., 100 GB per broker)
    - Network: Private subnets across 3 AZs

    Each instance runs a single Kafka broker with KRaft mode.
    Brokers form a quorum for leader election without ZooKeeper.
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
        Initialize EC2 Kafka Stack with 3 instances

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC to deploy EC2 instances
            config: Environment configuration dictionary
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Extract Kafka configuration
        kafka_config = config.get('kafka', {})
        instance_type_str = kafka_config.get('instance_type', 'c7i.large')
        instance_count = kafka_config.get('instance_count', 3)
        storage_gb = kafka_config.get('storage_gb', 100)
        environment = config.get('environment', 'development')

        # SSM Parameter path for broker discovery
        self.ssm_param_path = f'/ticketing/{environment}/kafka/brokers'

        # Determine CPU architecture based on instance type
        is_arm = any(
            instance_type_str.startswith(prefix)
            for prefix in ['t4g', 'm6g', 'm7g', 'c6g', 'c7g', 'r6g', 'r7g']
        )
        cpu_type = ec2.AmazonLinuxCpuType.ARM_64 if is_arm else ec2.AmazonLinuxCpuType.X86_64

        # ============= SSM Parameter for Broker Discovery =============
        # Each broker registers its IP; all brokers poll until 3 IPs are available
        # Format: "ip1,ip2,ip3" (comma-separated)
        # Note: SSM Parameter Store requires non-empty value, use placeholder
        self.broker_registry = ssm.StringParameter(
            self,
            'KafkaBrokerRegistry',
            parameter_name=self.ssm_param_path,
            string_value='pending',  # Placeholder, brokers will overwrite
            description=f'Kafka broker IPs for {environment} (auto-discovered)',
            tier=ssm.ParameterTier.STANDARD,
        )

        # ============= IAM Role for EC2 Instances =============
        self.instance_role = iam.Role(
            self,
            'KafkaInstanceRole',
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            description='IAM role for Kafka EC2 instances with SSM access',
            managed_policies=[
                # SSM Agent for remote management (optional)
                iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
            ],
        )

        # Grant read/write access to SSM Parameters (main + per-broker)
        self.broker_registry.grant_read(self.instance_role)
        self.broker_registry.grant_write(self.instance_role)

        # Grant access to per-broker SSM parameters (/ticketing/{env}/kafka/brokers/broker-*)
        self.instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    'ssm:GetParameter',
                    'ssm:PutParameter',
                ],
                resources=[
                    f'arn:aws:ssm:*:*:parameter{self.ssm_param_path}/broker-*',
                ],
            )
        )

        # ============= Security Group =============
        self.kafka_sg = ec2.SecurityGroup(
            self,
            'KafkaSecurityGroup',
            vpc=vpc,
            description='Security group for EC2 Kafka cluster (3 instances)',
            allow_all_outbound=True,
        )

        # Kafka broker port (9092) - all brokers use same port
        self.kafka_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9092),
            description='Kafka broker port',
        )

        # Kafka controller port (9093) - for KRaft consensus
        self.kafka_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(9093),
            description='Kafka controller port (KRaft)',
        )

        # SSH access (for debugging)
        self.kafka_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(22),
            description='SSH access from VPC',
        )

        # ============= Get Private Subnets (one per AZ) =============
        private_subnets = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnets

        if len(private_subnets) < instance_count:
            raise ValueError(
                f'Need {instance_count} subnets but only {len(private_subnets)} available'
            )

        # ============= Create Kafka Instances =============
        self.instances: list[ec2.Instance] = []
        instance_ips: list[str] = []

        for i in range(instance_count):
            node_id = i + 1
            subnet = private_subnets[i]

            # User data script for this broker (with SSM auto-discovery)
            user_data = self._create_user_data(
                node_id=node_id,
                ssm_param_path=self.ssm_param_path,
                total_brokers=instance_count,
            )

            # Block device (EBS for Kafka data)
            # Note: gp3 defaults to 3000 IOPS and 125 MB/s throughput
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

            # Create instance
            instance = ec2.Instance(
                self,
                f'KafkaBroker{node_id}',
                instance_name=f'kafka-broker-{node_id}',
                instance_type=ec2.InstanceType(instance_type_str),
                machine_image=ec2.MachineImage.latest_amazon_linux2023(cpu_type=cpu_type),
                vpc=vpc,
                vpc_subnets=ec2.SubnetSelection(subnets=[subnet]),
                security_group=self.kafka_sg,
                user_data=user_data,
                block_devices=block_devices,
                role=self.instance_role,  # IAM role for SSM access
            )

            self.instances.append(instance)
            instance_ips.append(instance.instance_private_ip)

            # Output for each instance
            CfnOutput(
                self,
                f'KafkaBroker{node_id}IP',
                value=instance.instance_private_ip,
                description=f'Kafka Broker {node_id} Private IP',
            )

        # ============= Update User Data with Actual IPs =============
        # Note: Due to circular dependency, we use placeholder and replace at runtime
        # The user data script discovers other brokers via Tags or SSM Parameter

        # ============= Bootstrap Servers =============
        # Format: broker1:9092,broker2:9092,broker3:9092
        self.bootstrap_servers = Fn.join(
            ',',
            [f'{ip}:9092' for ip in instance_ips],
        )

        CfnOutput(
            self,
            'KafkaBootstrapServers',
            value=self.bootstrap_servers,
            description='Kafka Bootstrap Servers (internal)',
            export_name='TicketingKafkaBootstrapServers',
        )

        CfnOutput(
            self,
            'KafkaSecurityGroupId',
            value=self.kafka_sg.security_group_id,
            description='Kafka Security Group ID',
        )

        CfnOutput(
            self,
            'KafkaBrokerRegistryPath',
            value=self.ssm_param_path,
            description='SSM Parameter path for Kafka broker discovery',
            export_name='TicketingKafkaBrokerRegistryPath',
        )

    def _create_user_data(
        self, *, node_id: int, ssm_param_path: str, total_brokers: int
    ) -> ec2.UserData:
        """
        Create user data script for a Kafka broker with SSM auto-discovery

        Args:
            node_id: Broker node ID (1, 2, or 3)
            ssm_param_path: SSM Parameter path for broker registry
            total_brokers: Total number of brokers to wait for

        Returns:
            UserData object with installation script
        """
        user_data = ec2.UserData.for_linux()

        user_data.add_commands(
            '#!/bin/bash',
            'set -ex',
            '',
            '# ============= Configuration =============',
            f'NODE_ID={node_id}',
            f'SSM_PARAM_PATH="{ssm_param_path}"',
            f'TOTAL_BROKERS={total_brokers}',
            '',
            '# ============= System Setup =============',
            'dnf update -y',
            'dnf install -y java-17-amazon-corretto-headless jq aws-cli tar gzip',
            '',
            '# ============= Get Instance Metadata (IMDSv2) =============',
            'TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")',
            'REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)',
            'OWN_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4)',
            'echo "This broker IP: $OWN_IP (Node ID: $NODE_ID, Region: $REGION)"',
            '',
            '# ============= Download and Install Kafka =============',
            'KAFKA_VERSION="4.1.1"',
            'SCALA_VERSION="2.13"',
            'cd /tmp',
            'curl -sLO "https://dlcdn.apache.org/kafka/${KAFKA_VERSION}/kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz"',
            'tar -xzf kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz',
            'mv kafka_${SCALA_VERSION}-${KAFKA_VERSION} /opt/kafka',
            'rm -f kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz',
            '',
            '# Create data and logs directories',
            'mkdir -p /opt/kafka/kraft-logs /var/log/kafka',
            'useradd -r -s /sbin/nologin kafka || true',
            'chown -R kafka:kafka /opt/kafka /var/log/kafka',
            '',
            '# ============= SSM Parameter Store: Register This Broker =============',
            '# Each broker writes to its own parameter to avoid race condition',
            'MY_SSM_PATH="${SSM_PARAM_PATH}/broker-${NODE_ID}"',
            'aws ssm put-parameter --name "$MY_SSM_PATH" --value "$OWN_IP" --type String --overwrite --region "$REGION"',
            'echo "Registered broker $NODE_ID ($OWN_IP) to $MY_SSM_PATH"',
            '',
            '# ============= Wait for All Brokers =============',
            'wait_for_brokers() {',
            '    local max_wait=300  # 5 minutes max',
            '    local waited=0',
            '    ',
            '    echo "Waiting for $TOTAL_BROKERS brokers to register..." >&2',
            '    ',
            '    while [ $waited -lt $max_wait ]; do',
            '        BROKER_IPS=""',
            '        BROKER_COUNT=0',
            '        ',
            "        # Read each broker's individual SSM parameter",
            '        for i in $(seq 1 $TOTAL_BROKERS); do',
            '            BROKER_IP=$(aws ssm get-parameter --name "${SSM_PARAM_PATH}/broker-${i}" --region "$REGION" --query "Parameter.Value" --output text 2>/dev/null || echo "")',
            '            if [ -n "$BROKER_IP" ] && [ "$BROKER_IP" != "None" ]; then',
            '                if [ -n "$BROKER_IPS" ]; then BROKER_IPS="$BROKER_IPS,"; fi',
            '                BROKER_IPS="${BROKER_IPS}${BROKER_IP}"',
            '                BROKER_COUNT=$((BROKER_COUNT + 1))',
            '            fi',
            '        done',
            '        ',
            '        echo "Registered brokers: $BROKER_COUNT/$TOTAL_BROKERS ($BROKER_IPS)" >&2',
            '        ',
            '        if [ "$BROKER_COUNT" -ge "$TOTAL_BROKERS" ]; then',
            '            echo "All $TOTAL_BROKERS brokers registered!" >&2',
            '            echo "$BROKER_IPS"',
            '            return 0',
            '        fi',
            '        ',
            '        sleep 5',
            '        waited=$((waited + 5))',
            '    done',
            '    ',
            '    echo "ERROR: Timeout waiting for all brokers" >&2',
            '    return 1',
            '}',
            '',
            '# Wait and get all broker IPs (in order: broker-1, broker-2, broker-3)',
            'BROKER_IPS=$(wait_for_brokers)',
            'if [ $? -ne 0 ]; then',
            '    echo "FATAL: Failed to get all broker IPs. Exiting."',
            '    exit 1',
            'fi',
            'echo "Final broker list: $BROKER_IPS"',
            '',
            '# ============= Build Quorum Voters String =============',
            'build_quorum_voters() {',
            '    local ips="$1"',
            '    local voters=""',
            '    local node=1',
            '    ',
            '    IFS="," read -ra IP_ARRAY <<< "$ips"',
            '    for ip in "${IP_ARRAY[@]}"; do',
            '        if [ -n "$voters" ]; then voters="$voters,"; fi',
            '        voters="${voters}${node}@${ip}:9093"',
            '        node=$((node + 1))',
            '    done',
            '    ',
            '    echo "$voters"',
            '}',
            '',
            'QUORUM_VOTERS=$(build_quorum_voters "$BROKER_IPS")',
            'echo "Controller Quorum Voters: $QUORUM_VOTERS"',
            '',
            '# Node ID is fixed based on CDK assignment (NODE_ID)',
            'ACTUAL_NODE_ID=$NODE_ID',
            'echo "This broker Node ID: $ACTUAL_NODE_ID"',
            '',
            '# ============= Create Kafka KRaft Configuration =============',
            'mkdir -p /opt/kafka/config/kraft',
            'cat > /opt/kafka/config/kraft/server.properties << EOF',
            '# KRaft Mode Configuration',
            'process.roles=broker,controller',
            'node.id=${ACTUAL_NODE_ID}',
            'controller.quorum.voters=${QUORUM_VOTERS}',
            '',
            '# Listeners',
            'listeners=PLAINTEXT://:9092,CONTROLLER://:9093',
            'advertised.listeners=PLAINTEXT://${OWN_IP}:9092',
            'controller.listener.names=CONTROLLER',
            'listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT',
            'inter.broker.listener.name=PLAINTEXT',
            '',
            '# Log Dirs',
            'log.dirs=/opt/kafka/kraft-logs',
            '',
            '# Topic Defaults',
            'num.partitions=6',
            'default.replication.factor=3',
            'min.insync.replicas=2',
            'offsets.topic.replication.factor=3',
            'transaction.state.log.replication.factor=3',
            'transaction.state.log.min.isr=2',
            '',
            '# Performance',
            'num.network.threads=3',
            'num.io.threads=8',
            'socket.send.buffer.bytes=102400',
            'socket.receive.buffer.bytes=102400',
            'socket.request.max.bytes=104857600',
            '',
            '# Log Retention',
            'log.retention.hours=168',
            'log.segment.bytes=1073741824',
            'log.retention.check.interval.ms=300000',
            '',
            '# Auto Create Topics',
            'auto.create.topics.enable=true',
            'EOF',
            '',
            '# Replace placeholders with actual values',
            'sed -i "s/\\${ACTUAL_NODE_ID}/$ACTUAL_NODE_ID/g" /opt/kafka/config/kraft/server.properties',
            'sed -i "s/\\${OWN_IP}/$OWN_IP/g" /opt/kafka/config/kraft/server.properties',
            'sed -i "s|\\${QUORUM_VOTERS}|$QUORUM_VOTERS|g" /opt/kafka/config/kraft/server.properties',
            '',
            '# ============= Format Storage (KRaft) =============',
            'CLUSTER_ID="MkU3OEVBNTcwNTJENDM2Qk"',
            '/opt/kafka/bin/kafka-storage.sh format -t $CLUSTER_ID -c /opt/kafka/config/kraft/server.properties --ignore-formatted',
            'chown -R kafka:kafka /opt/kafka/kraft-logs',
            '',
            '# ============= Create Systemd Service =============',
            'cat > /etc/systemd/system/kafka.service << EOF',
            '[Unit]',
            'Description=Apache Kafka Broker (KRaft Mode)',
            'After=network.target',
            '',
            '[Service]',
            'Type=simple',
            'User=kafka',
            'Group=kafka',
            'Environment="JAVA_HOME=/usr/lib/jvm/java-17-amazon-corretto"',
            'Environment="KAFKA_HEAP_OPTS=-Xmx2G -Xms2G"',
            'ExecStart=/opt/kafka/bin/kafka-server-start.sh /opt/kafka/config/kraft/server.properties',
            'ExecStop=/opt/kafka/bin/kafka-server-stop.sh',
            'Restart=on-failure',
            'RestartSec=10',
            'LimitNOFILE=100000',
            '',
            '[Install]',
            'WantedBy=multi-user.target',
            'EOF',
            '',
            'systemctl daemon-reload',
            'systemctl enable kafka.service',
            'systemctl start kafka.service',
            '',
            '# Wait for Kafka to start',
            'sleep 10',
            '',
            'echo "============================================"',
            'echo "Kafka broker $ACTUAL_NODE_ID started successfully!"',
            'echo "Broker IP: $OWN_IP"',
            'echo "Quorum: $QUORUM_VOTERS"',
            'echo "============================================"',
        )

        return user_data
