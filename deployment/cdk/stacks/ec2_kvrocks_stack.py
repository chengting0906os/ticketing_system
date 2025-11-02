"""
EC2 Kvrocks Stack - Self-hosted Redis-compatible storage on single EC2 instance
Runs Kvrocks binary directly (no Docker) with RocksDB backend

Architecture:
- 1 × EC2 instance (instance type from config.yml)
- Kvrocks binary (compiled from source)
- RocksDB backend for persistence
- EBS gp3 storage (size from config.yml)
- Cost: ~$12/month (vs Fargate+EFS $25/month)

Savings: $13/month (52% reduction)
Benefits: Better I/O performance with EBS, simpler deployment, lower cost

Configuration values come from deployment/config.yml:
- config['kvrocks']['instance_type'] (e.g., t4g.small)
- config['kvrocks']['storage_gb'] (e.g., 30)
- config['kvrocks']['port'] (default: 6666)
- config['kvrocks']['max_clients'] (default: 10000)
"""

from aws_cdk import CfnOutput, Stack, aws_ec2 as ec2
from constructs import Construct


class EC2KvrocksStack(Stack):
    """
    Self-hosted Kvrocks on single EC2 instance

    Configuration from config.yml:
    - Instance: config['kvrocks']['instance_type'] (e.g., t4g.small)
    - Storage: config['kvrocks']['storage_gb'] (e.g., 30 GB)
    - Port: config['kvrocks']['port'] (default: 6666)
    - Network: Private subnet
    - Cost: ~$12/month

    Single instance runs Kvrocks natively (no Docker),
    providing cost-effective and performant Redis alternative.
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
        Initialize EC2 Kvrocks Stack with single instance

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            vpc: VPC to deploy EC2 instance
            config: Environment configuration dictionary
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Extract Kvrocks configuration
        kvrocks_config = config.get('kvrocks', {})
        instance_type = kvrocks_config.get('instance_type', 't4g.small')
        storage_gb = kvrocks_config.get('storage_gb', 30)
        kvrocks_port = kvrocks_config.get('port', 6666)
        max_clients = kvrocks_config.get('max_clients', 10000)

        # ============= Security Group =============
        self.kvrocks_sg = ec2.SecurityGroup(
            self,
            'KvrocksSecurityGroup',
            vpc=vpc,
            description='Security group for EC2 Kvrocks instance',
            allow_all_outbound=True,
        )

        # Kvrocks port (default: 6666)
        self.kvrocks_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(kvrocks_port),
            description=f'Kvrocks port {kvrocks_port}',
        )

        # SSH access (for debugging)
        self.kvrocks_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(22),
            description='SSH access from VPC',
        )

        # ============= User Data Script =============
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            '#!/bin/bash',
            'set -e',
            '',
            '# Update system',
            'yum update -y',
            '',
            '# Install dependencies',
            'yum install -y gcc gcc-c++ make git autoconf automake libtool',
            '',
            '# Install CMake (required for Kvrocks)',
            'wget https://github.com/Kitware/CMake/releases/download/v3.28.0/cmake-3.28.0-linux-aarch64.tar.gz',
            'tar -xzf cmake-3.28.0-linux-aarch64.tar.gz -C /usr/local --strip-components=1',
            'rm cmake-3.28.0-linux-aarch64.tar.gz',
            '',
            '# Create kvrocks user',
            'useradd -r -s /bin/false kvrocks',
            '',
            '# Create directories',
            'mkdir -p /var/lib/kvrocks/data',
            'mkdir -p /var/log/kvrocks',
            'mkdir -p /etc/kvrocks',
            '',
            '# Clone and build Kvrocks',
            'cd /opt',
            'git clone https://github.com/apache/kvrocks.git',
            'cd kvrocks',
            'git checkout v2.13.0  # Latest stable version',
            './x.py build -DENABLE_OPENSSL=OFF -j $(nproc)',
            '',
            '# Install binary',
            'cp build/kvrocks /usr/local/bin/',
            'chmod +x /usr/local/bin/kvrocks',
            '',
            '# Create configuration file',
            "cat > /etc/kvrocks/kvrocks.conf << 'EOF'",
            '# Kvrocks Configuration',
            'bind 0.0.0.0',
            f'port {kvrocks_port}',
            'dir /var/lib/kvrocks/data',
            'log-dir /var/log/kvrocks',
            'log-level info',
            f'maxclients {max_clients}',
            'timeout 300',
            'daemonize no',
            'pidfile /var/run/kvrocks.pid',
            '',
            '# RocksDB Options',
            'rocksdb.compression lz4',
            'rocksdb.max_open_files 10000',
            'rocksdb.write_buffer_size 64',
            'rocksdb.max_write_buffer_number 4',
            'rocksdb.target_file_size_base 64',
            'rocksdb.max_background_jobs 4',
            '',
            '# Replication',
            'replica-read-only yes',
            'EOF',
            '',
            '# Set permissions',
            'chown -R kvrocks:kvrocks /var/lib/kvrocks',
            'chown -R kvrocks:kvrocks /var/log/kvrocks',
            'chown -R kvrocks:kvrocks /etc/kvrocks',
            '',
            '# Create systemd service',
            "cat > /etc/systemd/system/kvrocks.service << 'EOF'",
            '[Unit]',
            'Description=Kvrocks - Redis-compatible storage',
            'After=network.target',
            '',
            '[Service]',
            'Type=simple',
            'User=kvrocks',
            'Group=kvrocks',
            'ExecStart=/usr/local/bin/kvrocks -c /etc/kvrocks/kvrocks.conf',
            'Restart=always',
            'RestartSec=10',
            'LimitNOFILE=65536',
            '',
            '[Install]',
            'WantedBy=multi-user.target',
            'EOF',
            '',
            '# Enable and start Kvrocks',
            'systemctl daemon-reload',
            'systemctl enable kvrocks',
            'systemctl start kvrocks',
            '',
            'echo "Kvrocks started successfully!"',
        )

        # ============= Create Kvrocks Instance =============
        private_subnets = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnets

        self.instance = ec2.Instance(
            self,
            'KvrocksInstance',
            instance_type=ec2.InstanceType(instance_type),
            machine_image=ec2.MachineImage.latest_amazon_linux2(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[private_subnets[0]]),
            security_group=self.kvrocks_sg,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name='/dev/xvda',
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=storage_gb,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=True,
                        encrypted=True,
                    ),
                ),
            ],
        )

        # ============= Outputs =============
        CfnOutput(
            self,
            'KvrocksInstanceId',
            value=self.instance.instance_id,
            description='Kvrocks Instance ID',
        )

        CfnOutput(
            self,
            'KvrocksPrivateIP',
            value=self.instance.instance_private_ip,
            description='Kvrocks Instance Private IP',
        )

        # Connection endpoint
        self.kvrocks_endpoint = f'{self.instance.instance_private_ip}:{kvrocks_port}'

        CfnOutput(
            self,
            'KvrocksEndpoint',
            value=self.kvrocks_endpoint,
            description='Kvrocks connection endpoint (host:port)',
            export_name='TicketingKvrocksEndpoint',
        )
