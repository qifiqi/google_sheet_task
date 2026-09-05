import json
import pandas as pd

from app.services.performance_analysis.exporter import PerformanceReportExporterMixin
from app.services.performance_analysis.metrics import PerformanceMetricsMixin
from app.services.performance_analysis.result_mapper import PerformanceResultMapperMixin
from app.services.performance_analysis.sheet_reader import GoogleSheetAnalysisMixin
from app.services.performance_analysis.text_analysis import TextReturnAnalysisMixin

class XPLAnalyzer(
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
xpl_analyzer = XPLAnalyzer()

__all__ = ["XPLAnalyzer", "xpl_analyzer"]

if __name__ == "__main__":
    xpl_analyzer = XPLAnalyzer()
    # from d import data2
    # df = pd.DataFrame(data2)
    # df2 = pd.DataFrame(data2)
    # df2['index_return'] = df2['index_returns']
    # df2['start_return'] = df2['start_returns']
    # df['index_return'] = df['index_returns'] * 0.5
    # df['start_return'] = df['start_returns'] * 0.5

    from tests.d import data

    parsed_data = xpl_analyzer._parse_input_data(data)
    df2 = pd.DataFrame(parsed_data)
    df2['index_return'] = df2['daily_return']
    df2['start_return'] = df2['daily_return']
    print(json.dumps(xpl_analyzer._calculate_metrics_v1(df2.to_dict(orient='records')), ensure_ascii=False, indent=4))
    # print(json.dumps(xpl_analyzer._calculate_metrics_v1(df.to_dict(orient='records')),ensure_ascii=False))
    # print(json.dumps(xpl_analyzer._calculate_metrics_v1(df2.to_dict(orient='records')),ensure_ascii=False))
    # xpl_analyzer._calculate_metrics(parsed_data)
    # xpl_analyzer.analyze_v1('1jTXxqMzQXu52_eWt8_5qnnZB0EfRwjH9bfC79TpPcwM','data7y')
    # xpl_analyzer.get_google_sheet_data('1jTXxqMzQXu52_eWt8_5qnnZB0EfRwjH9bfC79TpPcwM','data7y')
    # xpl_analyzer.get_google_sheet_data('1BxinniyEdRwSx-tPi_3qMi_WjhYbEQVTyX3Mg_sQr5U','control')
