"""
票務系統最佳Partition配置策略
分析100萬張票的最佳分區方案
"""

from dataclasses import dataclass
from math import ceil

from src.shared.logging.loguru_io import Logger


@dataclass
class PartitionConfig:
    """Partition配置"""

    total_tickets: int
    partitions: int
    consumers: int
    partitions_per_consumer: int
    tickets_per_partition: int
    estimated_throughput: str
    memory_usage: str
    complexity: str
    recommendation: str


class TicketPartitionOptimizer:
    """票務系統Partition優化器"""

    def __init__(self, total_tickets: int = 50_000):
        self.total_tickets = total_tickets

    def analyze_configuration(self, partitions: int, consumers: int) -> PartitionConfig:
        """分析特定配置的優缺點"""
        partitions_per_consumer = ceil(partitions / consumers)
        tickets_per_partition = ceil(self.total_tickets / partitions)

        # 評估性能指標
        throughput = self._evaluate_throughput(partitions, consumers)
        memory = self._evaluate_memory_usage(partitions, consumers)
        complexity = self._evaluate_complexity(partitions, consumers)
        recommendation = self._get_recommendation(partitions, consumers)

        return PartitionConfig(
            total_tickets=self.total_tickets,
            partitions=partitions,
            consumers=consumers,
            partitions_per_consumer=partitions_per_consumer,
            tickets_per_partition=tickets_per_partition,
            estimated_throughput=throughput,
            memory_usage=memory,
            complexity=complexity,
            recommendation=recommendation,
        )

    def _evaluate_throughput(self, partitions: int, consumers: int) -> str:
        """評估吞吐量"""
        partitions_per_consumer = ceil(partitions / consumers)

        if partitions_per_consumer > 50:
            return '🔴 低 - Consumer負載過重'
        elif partitions_per_consumer > 20:
            return '🟡 中 - 可接受但不理想'
        elif partitions_per_consumer >= 5:
            return '🟢 高 - 良好平衡'
        else:
            return '🟡 中 - Consumer可能閒置'

    def _evaluate_memory_usage(self, partitions: int, consumers: int) -> str:
        """評估記憶體使用"""
        if partitions > 1000:
            return '🔴 高 - Metadata overhead過大'
        elif partitions > 500:
            return '🟡 中 - 需要監控'
        else:
            return '🟢 低 - 合理使用'

    def _evaluate_complexity(self, partitions: int, consumers: int) -> str:
        """評估管理複雜度"""
        partitions_per_consumer = ceil(partitions / consumers)

        if partitions > 1000 or partitions_per_consumer > 50:
            return '🔴 高 - 難以管理'
        elif partitions > 200 or partitions_per_consumer > 20:
            return '🟡 中 - 需要自動化工具'
        else:
            return '🟢 低 - 易於管理'

    def _get_recommendation(self, partitions: int, consumers: int) -> str:
        """獲得配置建議"""
        partitions_per_consumer = ceil(partitions / consumers)
        tickets_per_partition = ceil(self.total_tickets / partitions)

        issues = []

        if partitions_per_consumer > 50:
            issues.append('減少partition數量或增加consumer')

        if tickets_per_partition < 1000:
            issues.append('partition過度分割，建議合併')

        if partitions > 1000:
            issues.append('partition數量過多，增加管理複雜度')

        if consumers > partitions:
            issues.append('consumer數量超過partition，會有閒置')

        if not issues:
            return '✅ 配置合理'
        else:
            return '⚠️ 需要調整: ' + '; '.join(issues)


def compare_partition_strategies():
    """比較不同的partition策略"""

    optimizer = TicketPartitionOptimizer(total_tickets=1_000_000)

    # 測試不同配置
    configurations = [
        # (partitions, consumers, description)
        (2000, 20, '用戶原始配置'),
        (100, 20, '推薦配置1: 平衡型'),
        (200, 20, '推薦配置2: 高並發型'),
        (50, 10, '推薦配置3: 簡化型'),
        (400, 40, '推薦配置4: 大規模型'),
        (20, 5, '推薦配置5: 小規模型'),
    ]

    Logger.base.info('🎯 票務系統Partition配置比較')
    Logger.base.info('=' * 80)

    results = []

    for partitions, consumers, description in configurations:
        config = optimizer.analyze_configuration(partitions, consumers)
        results.append((description, config))

        Logger.base.info(f'\n📋 {description}')
        Logger.base.info(f'   Partition數量: {config.partitions}')
        Logger.base.info(f'   Consumer數量: {config.consumers}')
        Logger.base.info(f'   每Consumer的Partition: {config.partitions_per_consumer}')
        Logger.base.info(f'   每Partition的票數: {config.tickets_per_partition:,}')
        Logger.base.info(f'   吞吐量評估: {config.estimated_throughput}')
        Logger.base.info(f'   記憶體使用: {config.memory_usage}')
        Logger.base.info(f'   管理複雜度: {config.complexity}')
        Logger.base.info(f'   建議: {config.recommendation}')

    return results


def recommend_optimal_configuration():
    """推薦最佳配置"""

    Logger.base.info('\n🏆 票務系統最佳配置建議')
    Logger.base.info('=' * 50)

    recommendations = {
        '小型部署 (< 10萬張票)': {
            'partitions': 20,
            'consumers': 5,
            'reasoning': '簡單管理，足夠並發性',
        },
        '中型部署 (10-50萬張票)': {
            'partitions': 50,
            'consumers': 10,
            'reasoning': '平衡性能與複雜度',
        },
        '大型部署 (50-200萬張票)': {
            'partitions': 100,
            'consumers': 20,
            'reasoning': '高並發，可控複雜度',
        },
        '超大型部署 (200萬+張票)': {
            'partitions': 200,
            'consumers': 40,
            'reasoning': '最大化性能，需要運維團隊',
        },
    }

    for scenario, config in recommendations.items():
        Logger.base.info(f'\n🎯 {scenario}')
        Logger.base.info(f'   推薦Partition: {config["partitions"]}')
        Logger.base.info(f'   推薦Consumer: {config["consumers"]}')
        Logger.base.info(f'   理由: {config["reasoning"]}')


def partition_strategy_by_business_logic():
    """基於業務邏輯的分區策略"""

    Logger.base.info('\n🎪 基於業務邏輯的分區策略')
    Logger.base.info('=' * 50)

    strategies = {
        '按票價分區': {
            'description': 'VIP/一般/優惠票分別使用不同partition',
            'partitions': 30,  # 每種票價10個partition
            'consumers': 15,  # 每種票價5個consumer
            'advantages': ['優先級處理', '資源隔離', '靈活定價'],
        },
        '按座位區域分區': {
            'description': '依照場館座位區域(A區、B區、C區)分區',
            'partitions': 60,  # 每區20個partition
            'consumers': 20,  # 平均分配
            'advantages': ['座位管理簡單', '避免衝突', '地理分布'],
        },
        '按時間分區': {
            'description': '依照購票時間(尖峰/非尖峰)分區',
            'partitions': 40,  # 尖峰時段更多partition
            'consumers': 15,  # 動態調整
            'advantages': ['流量控制', '峰值處理', '用戶體驗'],
        },
        '混合策略': {
            'description': '結合票價、區域、時間的混合分區',
            'partitions': 100,
            'consumers': 25,
            'advantages': ['最大靈活性', '精細控制', '業務導向'],
        },
    }

    for strategy, details in strategies.items():
        Logger.base.info(f'\n🎯 {strategy}')
        Logger.base.info(f'   說明: {details["description"]}')
        Logger.base.info(f'   Partition: {details["partitions"]}')
        Logger.base.info(f'   Consumer: {details["consumers"]}')
        Logger.base.info(f'   優勢: {", ".join(details["advantages"])}')


def dynamic_scaling_strategy():
    """動態擴展策略"""

    Logger.base.info('\n🚀 動態擴展策略')
    Logger.base.info('=' * 50)

    scaling_rules = [
        {'condition': '每秒訂單 < 100', 'partitions': 20, 'consumers': 5, 'action': '基礎配置'},
        {
            'condition': '每秒訂單 100-500',
            'partitions': 50,
            'consumers': 10,
            'action': '增加consumer',
        },
        {
            'condition': '每秒訂單 500-1000',
            'partitions': 100,
            'consumers': 20,
            'action': '增加partition和consumer',
        },
        {
            'condition': '每秒訂單 > 1000',
            'partitions': 200,
            'consumers': 40,
            'action': '最大並發配置',
        },
    ]

    for rule in scaling_rules:
        Logger.base.info(f'\n📊 {rule["condition"]}')
        Logger.base.info(f'   Partition: {rule["partitions"]}')
        Logger.base.info(f'   Consumer: {rule["consumers"]}')
        Logger.base.info(f'   動作: {rule["action"]}')


if __name__ == '__main__':
    # 執行分析
    compare_partition_strategies()
    recommend_optimal_configuration()
    partition_strategy_by_business_logic()
    dynamic_scaling_strategy()
