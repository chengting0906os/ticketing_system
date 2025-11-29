"""
EC2 Kvrocks Stack - Redis-compatible storage on EC2 with kvrocks-fpm
Runs Kvrocks binary (pre-compiled .deb) on Ubuntu EC2 instance

Architecture:
- 1 × EC2 instance (instance type from config.yml)
- Ubuntu 24.04 LTS x86_64 with kvrocks-fpm v2.13.0-1
- Systemd service for process management
- Storage: NVMe instance store (m6id, i4i) or EBS (configurable)
- Auto Scaling Group (single instance) for automatic restart on failure

Storage Options:
- NVMe (m6id.large): $82/month, 118 GB, ~40K IOPS
- NVMe (i4i.large): $165/month, 468 GB, 50K+ IOPS
- EBS (gp3): Configurable IOPS and throughput

Benefits: Fast deployment, native binary performance, high IOPS with NVMe
"""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_servicediscovery as sd
from constructs import Construct


class EC2KvrocksStack(Stack):
    """
    EC2 Kvrocks Stack with kvrocks-fpm (pre-compiled binary)

    Configuration from config.yml:
    - Instance: config['kvrocks']['instance_type'] (e.g., m6id.large, i4i.large)
    - Storage Type: config['kvrocks']['storage_type'] ('nvme' or 'ebs')
    - Port: config['kvrocks']['port'] (default: 6666)

    NVMe Configuration (storage_type='nvme'):
    - Uses instance store (m6id: 118GB, i4i: 468GB)
    - High IOPS (40K-50K+)
    - Data lost on stop/start (reboot preserves data)

    EBS Configuration (storage_type='ebs'):
    - Storage: config['kvrocks']['storage_gb'] (e.g., 30 GB)
    - Configurable IOPS/throughput
    - Data persists across stop/start

    Single EC2 instance runs Kvrocks native binary with systemd,
    providing fast deployment without compilation.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        namespace: sd.INamespace,
        config: dict,
        **kwargs,
    ) -> None:
        """
        Initialize EC2 Kvrocks Stack with kvrocks-fpm

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC to deploy EC2 instance
            namespace: Service discovery namespace
            config: Environment configuration dictionary
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Extract Kvrocks configuration
        kvrocks_config = config.get('kvrocks', {})
        instance_type_str = kvrocks_config.get('instance_type', 't3.small')
        storage_type = kvrocks_config.get('storage_type', 'ebs')  # 'ebs' or 'nvme'
        storage_gb = kvrocks_config.get('storage_gb', 30)  # Only used for EBS
        kvrocks_port = kvrocks_config.get('port', 6666)
        max_clients = kvrocks_config.get('max_clients', 10000)

        # EBS volume configuration (only used when storage_type='ebs')
        ebs_volume_type = kvrocks_config.get('ebs_volume_type', 'gp3')
        ebs_iops = kvrocks_config.get('ebs_iops', None)  # None = use default for volume type
        ebs_throughput = kvrocks_config.get('ebs_throughput', None)  # None = use default

        # ============= Security Group for EC2 =============
        self.ec2_sg = ec2.SecurityGroup(
            self,
            'KvrocksEC2SecurityGroup',
            vpc=vpc,
            description='Security group for Kvrocks EC2 instance',
            allow_all_outbound=True,
        )

        # Kvrocks port (default: 6666)
        self.ec2_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(kvrocks_port),
            description=f'Kvrocks port {kvrocks_port}',
        )

        # SSH access (for debugging)
        self.ec2_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(22),
            description='SSH access from VPC',
        )

        # Export security group for other stacks to reference
        self.security_group = self.ec2_sg

        # ============= Service Discovery Integration (Create first) =============
        # Register EC2 instance IP with Cloud Map for service discovery
        # Note: This will use the private IP of the EC2 instance
        from aws_cdk import Duration

        self.service_discovery = sd.Service(
            self,
            'KvrocksServiceDiscovery',
            namespace=namespace,
            name='kvrocks',
            dns_record_type=sd.DnsRecordType.A,
            dns_ttl=Duration.seconds(10),
            description='Kvrocks EC2 instance service discovery',
        )

        # ============= IAM Role for EC2 Instance =============
        instance_role = iam.Role(
            self,
            'KvrocksInstanceRole',
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
            ],
        )

        # Grant permission to register instances in Service Discovery
        instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    'servicediscovery:RegisterInstance',
                    'servicediscovery:DeregisterInstance',
                ],
                resources=[self.service_discovery.service_arn],
            )
        )
        instance_role.add_to_policy(
            iam.PolicyStatement(actions=['ec2:DescribeInstances'], resources=['*'])
        )

        # ============= User Data for Kvrocks Installation (kvrocks-fpm) =============
        user_data = ec2.UserData.for_linux()

        # Generate mount commands based on storage type
        if storage_type == 'nvme':
            # NVMe instance store (m6id, i4i, etc.) - use first instance store volume
            mount_commands = [
                '# Mount NVMe instance store for Kvrocks data',
                'mkdir -p /data/kvrocks',
                '',
                '# Use first NVMe instance store (nvme1n1 is typically the first instance store)',
                'DATA_DEVICE="/dev/nvme1n1"',
                '',
                'if [ ! -b "$DATA_DEVICE" ]; then',
                '  echo "ERROR: NVMe instance store $DATA_DEVICE not found"',
                '  exit 1',
                'fi',
                '',
                'echo "Using NVMe instance store: $DATA_DEVICE"',
                '',
                '# Clean up any previous mounts',
                'umount /data/kvrocks || true',
                '',
                '# Format NVMe (instance store is always empty on first boot)',
                'echo "Formatting $DATA_DEVICE with ext4..."',
                'mkfs.ext4 -F "$DATA_DEVICE"',
                '',
                '# Mount the NVMe volume',
                'echo "Mounting $DATA_DEVICE to /data/kvrocks..."',
                'mount "$DATA_DEVICE" /data/kvrocks',
                '',
                '# Note: Do NOT add to fstab - instance store may not exist after stop/start',
            ]
        else:
            # EBS volume - use existing logic to find 30GB volume
            mount_commands = [
                '# Mount EBS volume for Kvrocks data',
                'mkdir -p /data/kvrocks',
                '',
                '# Find data volume (30GB EBS, not the root volume)',
                '# On NVMe instances, find the 30GB volume (our data disk)',
                'DATA_DEVICE=""',
                'for dev in /dev/nvme[0-9]n1; do',
                '  size=$(lsblk -b -d -n -o SIZE "$dev" 2>/dev/null || echo 0)',
                '  # 30GB = 32212254720 bytes, allow 10% variance',
                '  if [ "$size" -gt 29000000000 ] && [ "$size" -lt 35000000000 ]; then',
                '    DATA_DEVICE="$dev"',
                '    break',
                '  fi',
                'done',
                '',
                'if [ -z "$DATA_DEVICE" ]; then',
                '  echo "ERROR: Could not find 30GB data volume"',
                '  exit 1',
                'fi',
                '',
                'echo "Data device found: $DATA_DEVICE"',
                '',
                '# Clean up any previous mounts',
                'umount /data/kvrocks || true',
                '',
                '# Check filesystem and repair if needed',
                'e2fsck -p "$DATA_DEVICE" || echo "fsck skipped or completed with warnings"',
                '',
                '# Format if no filesystem exists',
                'if ! blkid -s TYPE "$DATA_DEVICE" | grep -q TYPE; then',
                '  echo "Formatting $DATA_DEVICE with ext4..."',
                '  mkfs.ext4 "$DATA_DEVICE"',
                'fi',
                '',
                '# Mount the data volume',
                'echo "Mounting $DATA_DEVICE to /data/kvrocks..."',
                'mount "$DATA_DEVICE" /data/kvrocks',
                '',
                '# Add to fstab if not already present (using _netdev for network devices)',
                'if ! grep -q "/data/kvrocks" /etc/fstab; then',
                '  echo "$DATA_DEVICE /data/kvrocks ext4 defaults,_netdev 0 2" >> /etc/fstab',
                'fi',
            ]

        user_data.add_commands(
            '#!/bin/bash',
            'set -x  # Enable debug output',
            '',
            '# Update package list (no upgrade to avoid dpkg lock issues)',
            'apt-get update -y',
            'apt-get install -y wget redis-tools',
            '',
            '# Install AWS CLI v2 using snap (Ubuntu 24.04 compatible)',
            'snap install aws-cli --classic',
            '',
            *mount_commands,
            '',
            '# Download and install kvrocks-fpm (pre-compiled .deb for amd64)',
            'cd /tmp',
            'wget https://github.com/RocksLabs/kvrocks-fpm/releases/download/202510222/kvrocks_2.13.0-1_amd64.deb',
            'dpkg -i kvrocks_2.13.0-1_amd64.deb',
            '',
            '# Create data and log directories with proper permissions',
            'mkdir -p /data/kvrocks/data /data/kvrocks/logs',
            'chmod 755 /data/kvrocks/logs',
            'chown -R root:root /data/kvrocks',
            '',
            '# Create Kvrocks configuration',
            'mkdir -p /etc/kvrocks',
            'cat > /etc/kvrocks/kvrocks.conf <<EOF',
            'bind 0.0.0.0',
            f'port {kvrocks_port}',
            'dir /data/kvrocks/data',
            'log-dir /data/kvrocks/logs',
            'log-level info',
            f'maxclients {max_clients}',
            'daemonize no',
            'EOF',
            '',
            '# Create systemd service (using /usr/bin for kvrocks-fpm)',
            'cat > /etc/systemd/system/kvrocks.service <<EOF',
            '[Unit]',
            'Description=Kvrocks Server',
            'After=network.target',
            '',
            '[Service]',
            'Type=simple',
            'User=root',
            'ExecStart=/usr/bin/kvrocks -c /etc/kvrocks/kvrocks.conf',
            'Restart=always',
            'RestartSec=3',
            '',
            '[Install]',
            'WantedBy=multi-user.target',
            'EOF',
            '',
            '# Start Kvrocks',
            'systemctl daemon-reload',
            'systemctl enable kvrocks',
            'systemctl start kvrocks',
            '',
            '# Wait for Kvrocks to be ready',
            'sleep 5',
            'echo "Kvrocks installation complete!"',
            '',
            '# Register instance to AWS Cloud Map Service Discovery',
            '# Use IMDSv2 (more secure) to get instance metadata',
            'TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null)',
            'INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)',
            'PRIVATE_IP=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4 2>/dev/null)',
            'REGION=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null)',
            f'SERVICE_ID="{self.service_discovery.service_id}"',
            '',
            'echo "Registering instance to Service Discovery..."',
            'echo "  Instance ID: $INSTANCE_ID"',
            'echo "  Private IP: $PRIVATE_IP"',
            'echo "  Region: $REGION"',
            'echo "  Service ID: $SERVICE_ID"',
            '',
            'aws servicediscovery register-instance \\',
            '  --region $REGION \\',
            '  --service-id $SERVICE_ID \\',
            '  --instance-id $INSTANCE_ID \\',
            '  --attributes AWS_INSTANCE_IPV4=$PRIVATE_IP',
            '',
            'echo "✅ Instance registered to Service Discovery: $INSTANCE_ID -> $PRIVATE_IP"',
        )

        # ============= Launch Template =============
        # Build block devices list based on storage type
        block_devices = [
            ec2.BlockDevice(
                device_name='/dev/xvda',  # Root volume
                volume=ec2.BlockDeviceVolume.ebs(
                    volume_size=30,  # 30 GB for OS
                    volume_type=ec2.EbsDeviceVolumeType.GP3,
                    delete_on_termination=True,
                    encrypted=True,
                ),
            ),
        ]

        # Only add EBS data volume if storage_type is 'ebs'
        # NVMe instances (m6id, i4i) use instance store, not EBS
        if storage_type == 'ebs':
            block_devices.append(
                ec2.BlockDevice(
                    device_name='/dev/xvdf',  # Data volume for Kvrocks
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=storage_gb,
                        volume_type=self._get_volume_type(ebs_volume_type),
                        iops=ebs_iops,  # None = use default
                        throughput=ebs_throughput,  # None = use default
                        delete_on_termination=True,  # Clean up on termination
                        encrypted=True,
                    ),
                )
            )

        launch_template = ec2.LaunchTemplate(
            self,
            'KvrocksLaunchTemplate',
            instance_type=ec2.InstanceType(instance_type_str),
            machine_image=ec2.MachineImage.from_ssm_parameter(
                '/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id'
            ),
            security_group=self.ec2_sg,
            role=instance_role,
            user_data=user_data,
            block_devices=block_devices,
        )

        # ============= Auto Scaling Group (single instance) =============
        self.asg = autoscaling.AutoScalingGroup(
            self,
            'KvrocksASG',
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            launch_template=launch_template,
            min_capacity=1,
            max_capacity=1,
            desired_capacity=1,
        )

        # Tag instances for EventBridge filtering
        from aws_cdk import Tags

        Tags.of(self.asg).add('Service', 'kvrocks')
        Tags.of(self.asg).add('ManagedBy', 'ServiceDiscovery')

        # ============= Auto-Deregistration on Instance Termination =============
        # Lambda function to deregister instance from Service Discovery
        deregister_lambda = lambda_.Function(
            self,
            'DeregisterLambda',
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler='index.handler',
            code=lambda_.Code.from_inline(f'''
import boto3
import json

ec2 = boto3.client('ec2')
servicediscovery = boto3.client('servicediscovery')

def handler(event, context):
    """Deregister EC2 instance from Service Discovery on termination"""
    print(f"Received event: {{json.dumps(event)}}")

    # Extract instance ID from EC2 instance state change event
    instance_id = event['detail']['instance-id']
    service_id = '{self.service_discovery.service_id}'

    # Verify this is a KVrocks instance by checking tags
    try:
        response = ec2.describe_tags(
            Filters=[
                {{'Name': 'resource-id', 'Values': [instance_id]}},
                {{'Name': 'key', 'Values': ['Service']}},
                {{'Name': 'value', 'Values': ['kvrocks']}}
            ]
        )
        if not response.get('Tags'):
            print(f"Instance {{instance_id}} is not a KVrocks instance, skipping")
            return {{'statusCode': 200, 'body': 'Not a KVrocks instance'}}
    except Exception as e:
        print(f"Failed to check tags: {{str(e)}}")
        # Continue anyway - better to deregister than leave stale entry

    print(f"Deregistering KVrocks instance {{instance_id}} from service {{service_id}}")

    try:
        response = servicediscovery.deregister_instance(
            ServiceId=service_id,
            InstanceId=instance_id
        )
        print(f"Deregistration successful: {{response}}")
        return {{'statusCode': 200, 'body': 'Success'}}
    except Exception as e:
        print(f"Deregistration failed: {{str(e)}}")
        # Don't fail - instance is already terminating
        return {{'statusCode': 200, 'body': f'Failed but continuing: {{str(e)}}' }}
'''),
            timeout=Duration.seconds(30),
            description='Deregister KVrocks instance from Service Discovery on termination',
        )

        # Grant Lambda permissions
        deregister_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=['servicediscovery:DeregisterInstance'],
                resources=[self.service_discovery.service_arn],
            )
        )
        deregister_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=['ec2:DescribeTags'],
                resources=['*'],  # Read-only, requires '*'
            )
        )

        # EventBridge rule to trigger Lambda on EC2 instance termination
        # Triggers on: stopping, terminated, shutting-down states
        events.Rule(
            self,
            'InstanceTerminationRule',
            description='Deregister KVrocks from Service Discovery on EC2 termination',
            event_pattern=events.EventPattern(
                source=['aws.ec2'],
                detail_type=['EC2 Instance State-change Notification'],
                detail={
                    'state': ['shutting-down', 'terminated', 'stopping'],
                },
            ),
            targets=[targets.LambdaFunction(deregister_lambda)],
        )

        # ============= Outputs =============
        # Service discovery endpoint
        self.kvrocks_endpoint = f'kvrocks.{namespace.namespace_name}:{kvrocks_port}'

        CfnOutput(
            self,
            'KvrocksEndpoint',
            value=self.kvrocks_endpoint,
            description='Kvrocks connection endpoint (host:port via Service Discovery)',
        )

        CfnOutput(
            self,
            'KvrocksASGName',
            value=self.asg.auto_scaling_group_name,
            description='Auto Scaling Group name for Kvrocks EC2',
        )

        CfnOutput(
            self,
            'KvrocksSecurityGroupId',
            value=self.ec2_sg.security_group_id,
            description='Security Group ID for Kvrocks EC2',
        )

    def _get_volume_type(self, volume_type_str: str) -> ec2.EbsDeviceVolumeType:
        """
        Map volume type string to CDK enum

        Args:
            volume_type_str: Volume type string from config (e.g., 'gp3', 'io2')

        Returns:
            EbsDeviceVolumeType enum value
        """
        volume_type_map = {
            'gp2': ec2.EbsDeviceVolumeType.GP2,
            'gp3': ec2.EbsDeviceVolumeType.GP3,
            'io1': ec2.EbsDeviceVolumeType.IO1,
            'io2': ec2.EbsDeviceVolumeType.IO2,
            'st1': ec2.EbsDeviceVolumeType.ST1,
            'sc1': ec2.EbsDeviceVolumeType.SC1,
        }
        return volume_type_map.get(volume_type_str.lower(), ec2.EbsDeviceVolumeType.GP3)
