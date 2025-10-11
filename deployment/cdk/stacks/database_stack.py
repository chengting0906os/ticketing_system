"""
Database Stack for Ticketing System
Manages RDS PostgreSQL instance for production environment
"""

from aws_cdk import Duration, RemovalPolicy, Stack, aws_ec2 as ec2, aws_rds as rds
from constructs import Construct


class DatabaseStack(Stack):
    """
    Creates RDS PostgreSQL database for production

    Note: This is for AWS production deployment only.
    For local development, continue using Docker Compose.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============= VPC (網路隔離) =============

        # 創建 VPC 或使用現有的
        vpc = ec2.Vpc(
            self,
            'TicketingVpc',
            max_azs=2,  # 使用兩個可用區域（高可用）
            nat_gateways=1,  # NAT Gateway 用於私有子網連外網
        )

        # ============= 資料庫認證（安全） =============

        # 自動生成並安全存儲資料庫密碼
        db_credentials = rds.Credentials.from_generated_secret(
            username='py_arch_lab',
            secret_name='ticketing-db-credentials',
        )

        # ============= Security Group (防火牆) =============

        # 創建安全群組，只允許特定來源訪問
        db_security_group = ec2.SecurityGroup(
            self,
            'DatabaseSecurityGroup',
            vpc=vpc,
            description='Security group for Ticketing System database',
            allow_all_outbound=False,  # 不允許資料庫主動連外
        )

        # ============= RDS PostgreSQL Instance =============

        # 創建資料庫實例
        db_instance = rds.DatabaseInstance(
            self,
            'TicketingDatabase',
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16  # PostgreSQL 16
            ),
            # 實例大小（生產環境建議）
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3,  # t3 系列
                ec2.InstanceSize.MICRO,  # t3.micro (免費方案)
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS  # 私有子網
            ),
            security_groups=[db_security_group],
            # 資料庫設定
            database_name='ticketing_system_db',
            credentials=db_credentials,
            # 儲存設定
            allocated_storage=20,  # 20 GB
            max_allocated_storage=100,  # 自動擴展到 100 GB
            storage_encrypted=True,  # 加密存儲
            storage_type=rds.StorageType.GP3,  # General Purpose SSD
            # 高可用性設定
            multi_az=False,  # 開發環境設為 False，生產環境設為 True
            # 備份設定
            backup_retention=Duration.days(7),  # 保留 7 天備份
            preferred_backup_window='03:00-04:00',  # 台灣時間凌晨備份
            # 維護視窗
            preferred_maintenance_window='sun:04:00-sun:05:00',  # 週日凌晨維護
            # 刪除保護
            deletion_protection=True,  # 防止誤刪
            removal_policy=RemovalPolicy.SNAPSHOT,  # 刪除 stack 時創建快照
            # 監控
            cloudwatch_logs_exports=['postgresql'],  # 匯出日誌到 CloudWatch
            # 性能洞察
            enable_performance_insights=True,
            performance_insight_retention=rds.PerformanceInsightRetention.DEFAULT,
            # 自動升級
            auto_minor_version_upgrade=True,
        )

        # ============= Outputs (輸出連線資訊) =============

        from aws_cdk import CfnOutput

        # 輸出資料庫連線端點
        CfnOutput(
            self,
            'DatabaseEndpoint',
            value=db_instance.db_instance_endpoint_address,
            description='RDS PostgreSQL endpoint',
        )

        # 輸出資料庫 Secret ARN (包含密碼)
        CfnOutput(
            self,
            'DatabaseSecretArn',
            value=db_instance.secret.secret_arn if db_instance.secret else 'N/A',
            description='ARN of the secret containing database credentials',
        )

        # 輸出安全群組 ID
        CfnOutput(
            self,
            'DatabaseSecurityGroupId',
            value=db_security_group.security_group_id,
            description='Security Group ID for database access',
        )

        # 保存屬性供其他 stack 使用
        self.database = db_instance
        self.db_security_group = db_security_group


class DatabaseStackForLocalStack(Stack):
    """
    Simplified database stack for LocalStack testing
    Note: LocalStack RDS support is limited, recommended to use Docker Compose instead
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # LocalStack 不完全支援 RDS，這裡只是示範
        # 實際開發建議繼續使用 Docker Compose

        from aws_cdk import CfnOutput

        CfnOutput(
            self,
            'Note',
            value='For local development, use Docker Compose (make docker-up)',
            description='LocalStack RDS support is limited',
        )
