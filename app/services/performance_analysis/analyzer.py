from app.services.performance_analysis.exporter import PerformanceReportExporterMixin
from app.services.performance_analysis.metrics import PerformanceMetricsMixin
from app.services.performance_analysis.result_mapper import PerformanceResultMapperMixin
from app.services.performance_analysis.sheet_reader import GoogleSheetAnalysisMixin
from app.services.performance_analysis.text_analysis import TextReturnAnalysisMixin

class PerformanceAnalyzer(
    PerformanceReportExporterMixin,
    PerformanceResultMapperMixin,
    GoogleSheetAnalysisMixin,
    TextReturnAnalysisMixin,
    PerformanceMetricsMixin,
):
    """
    Excel数据收益率分析器
    负责处理Excel数据并计算相关指标
    """

    def __init__(self):
        """初始化分析过程中复用的数据容器和指标缓存。"""
        self.data = []
        self.metrics = {}

# 创建全局实例
performance_analyzer = PerformanceAnalyzer()

__all__ = ["PerformanceAnalyzer", "performance_analyzer"]
