"""Google Sheet adapters for performance analysis."""

from typing import Any, Dict

import pandas as pd

from app.services.config_manager import get_config_manager
from app.services.google_sheet_client import GoogleSheet
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleSheetAnalysisMixin:
    def analyze_v1(self, spreadsheet_id: str, google_sheet_name: str) -> Dict[str, Any]:
        """
        分析输入的Excel数据并返回结果和指标

        """
        try:
            # from app.services.da import data
            # parsed_data = self._parse_input_data(data)
            _data, _data_result, sheet_df = self.get_google_sheet_data(spreadsheet_id, google_sheet_name)
            # 计算指标
            metrics = self._calculate_metrics_v1(_data)

            metrics['sheet_result'] = _data_result
            # 准备返回结果
            return {
                'status': 'success',
                'results': metrics,
                # 'metrics': metrics
            }

        except Exception as e:
            logger.error(f"分析数据时出错: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'message': f"分析数据时出错: {str(e)}"
            }

    def _init_google_sheet(self, spreadsheet_id, sheet_name):
        """初始化Google Sheet连接"""
        try:
            config_data = get_config_manager().get_all_configs()
            token_file = config_data.get('token_file',
                                         r'D:\Users\Administrator\Desktop\谷歌参数批量校验\data\token.json')
            proxy_url = config_data.get('proxy_url', None)

            google_sheet = GoogleSheet(spreadsheet_id, sheet_name, token_file, proxy_url)
            if not google_sheet.worksheet:
                raise Exception("请先选择工作表")
            return google_sheet
        except Exception as e:
            error_msg = f"初始化Google Sheet连接失败: {str(e)}"
            raise error_msg

    @staticmethod
    def _parse_google_sheet_dates(date_series: pd.Series) -> pd.Series:
        """兼容 Google Sheet 中混合的序列日期和字符串日期。"""
        excel_base = pd.Timestamp('1899-12-30')
        text_series = date_series.astype(str).str.strip()
        numeric_values = pd.to_numeric(text_series, errors='coerce')
        parsed_dates = pd.Series(pd.NaT, index=date_series.index, dtype='datetime64[ns]')

        numeric_mask = numeric_values.notna()
        if numeric_mask.any():
            parsed_dates.loc[numeric_mask] = pd.to_timedelta(
                numeric_values.loc[numeric_mask],
                unit='d'
            ) + excel_base

        text_mask = (~numeric_mask) & text_series.ne('') & text_series.ne('nan') & text_series.ne('None')
        if text_mask.any():
            parsed_dates.loc[text_mask] = pd.to_datetime(
                text_series.loc[text_mask],
                errors='coerce'
            )

        return parsed_dates

    def get_google_sheet_data(self, spreadsheet_id: str, google_sheet_name: str) -> tuple[Any, dict[
        Any, Any], pd.DataFrame] | None:
        """读取 Google Sheet 数据并转换为分析所需的数据框。"""
        google_sheet = self._init_google_sheet(spreadsheet_id, google_sheet_name)
        title = google_sheet.title.upper()

        if 'C7.0.3' in title:
            last_now_num = google_sheet.get_last_row("CC")
            if last_now_num < 2:
                raise ValueError("C7.0.3 未找到 OHLC K线数据")

            ohlc_rows = google_sheet.get_range_2d(f'CC2:CG{last_now_num}', 'UNFORMATTED_VALUE')
            start_return_rows = google_sheet.get_range_2d(f'L2:L{last_now_num}', 'UNFORMATTED_VALUE')
            result_rows = google_sheet.get_range_2d('C2:D20', 'FORMATTED_VALUE')
            sheet_df = pd.DataFrame(ohlc_rows, columns=['date', 'open', 'high', 'low', 'close'])
            sheet_df['date'] = self._parse_google_sheet_dates(sheet_df['date'])
            sheet_df['close'] = pd.to_numeric(sheet_df['close'], errors='coerce')
            if sheet_df['close'].isna().any() or sheet_df['close'].iloc[0] == 0:
                raise ValueError('C7.0.3 OHLC 收盘价包含无效值')

            start_returns = pd.to_numeric(
                pd.Series([row[0] if row else None for row in start_return_rows]),
                errors='coerce',
            )
            if len(start_returns) != len(sheet_df) or start_returns.isna().any():
                raise ValueError('C7.0.3 strat return% 数据不完整')

            sheet_df['index_return'] = sheet_df['close'] / sheet_df['close'].iloc[0] - 1
            sheet_df['start_return'] = start_returns.to_numpy()
            _data = sheet_df[['date', 'index_return', 'start_return']].to_dict(orient='records')
            _data_result = {
                row[0]: row[1]
                for row in result_rows
                if len(row) >= 2 and row[0] not in ('', 'year#')
            }
            return _data, _data_result, sheet_df

        if 'C7' in title:
            last_now_num = google_sheet.get_last_row("A")
            if last_now_num < 10:
                last_now_num = 30
            sheet_data = google_sheet.get_range_2d(f'A2:N{last_now_num}', 'UNFORMATTED_VALUE')
            sheet_df = pd.DataFrame(sheet_data, columns=[
                'date', 'values_B', 'result_key_C', 'result_values_D', 'year_start_E',
                'year_beats_F', 'model_date_G', 'model_values_H', 'net_value_I', 'index_return', "index_DD_K",
                "start_return", "index_beats_M", "start_DD_N"])

            # Excel/Google Sheets 的基准日期是 1899-12-30
            sheet_df["date"] = self._parse_google_sheet_dates(sheet_df["date"])

            _data = sheet_df[['date', 'index_return', 'start_return']]

            _data = _data.to_dict(orient='records')

            _data_result = {}

            for item in sheet_df[['result_key_C', 'result_values_D']].to_dict(orient='records'):
                if item['result_key_C'] in ['', 'year#']:
                    continue

                _data_result[item['result_key_C']] = item['result_values_D']

            return _data, _data_result, sheet_df

        if 'C5' in title:
            last_now_num = google_sheet.get_last_row("A")
            if last_now_num < 10:
                last_now_num = 30
            sheet_data = google_sheet.get_range_2d(f'A2:N{last_now_num}', 'UNFORMATTED_VALUE')
            sheet_df = pd.DataFrame(sheet_data, columns=[
                'date', 'values_B', 'result_key_C', 'result_values_D', 'year_start_E',
                'year_beats_F', 'model_date_G', 'model_values_H', 'net_value_I', 'index_return', "index_DD_K",
                "start_return", "index_beats_M", "start_DD_N"])

            # Excel/Google Sheets 的基准日期是 1899-12-30
            sheet_df["date"] = self._parse_google_sheet_dates(sheet_df["date"])

            _data = sheet_df[['date', 'index_return', 'start_return']]

            _data = _data.to_dict(orient='records')

            _data_result = {}

            for item in sheet_df[['result_key_C', 'result_values_D']].to_dict(orient='records'):
                if item['result_key_C'] in ['', 'year#']:
                    continue

                _data_result[item['result_key_C']] = item['result_values_D']

            return _data, _data_result, sheet_df

        elif 'C4' in title:
            last_now_num = google_sheet.get_last_row("A")
            if last_now_num < 10:
                last_now_num = 30
            sheet_data = google_sheet.get_range_2d(f'A2:N{last_now_num}', 'UNFORMATTED_VALUE')
            sheet_df = pd.DataFrame(sheet_data, columns=[
                'date', 'values_B', 'result_key_C', 'result_values_D', 'year_start_E',
                'year_beats_F', 'model_date_G', 'model_values_H', 'net_value_I', 'index_return', "index_DD_K",
                "start_return", "index_beats_M", "start_DD_N"])
            # Excel/Google Sheets 的基准日期是 1899-12-30
            sheet_df["date"] = self._parse_google_sheet_dates(sheet_df["date"])

            _data = sheet_df[['date', 'index_return', 'start_return']]

            _data = _data.to_dict(orient='records')

            _data_result = {}

            for item in sheet_df[['result_key_C', 'result_values_D']].to_dict(orient='records'):
                if item['result_key_C'] in ['', 'year#']:
                    continue

                _data_result[item['result_key_C']] = item['result_values_D']

            return _data, _data_result, sheet_df


        elif 'C3' in title or 'Charting:3'.upper() in title:
            last_now_num = google_sheet.get_last_row("D")
            if last_now_num < 10:
                last_now_num = 30
            sheet_data = google_sheet.get_range_2d(f'A2:Q{last_now_num}', 'UNFORMATTED_VALUE')
            sheet_df = pd.DataFrame(sheet_data, columns=[
                'Parameter_A', 'Value_A', '_C', 'date', 'data_E',
                '_F', '_G', 'Parameter_H', 'Value_I', 'net_value_J', "index_return", 'index_DD_K', '_M', "_N",
                "start_return", "_P", "start_DD_Q"])

            # Excel/Google Sheets 的基准日期是 1899-12-30
            sheet_df["date"] = self._parse_google_sheet_dates(sheet_df["date"])

            _data = sheet_df[['date', 'index_return', 'start_return']].to_dict(orient='records')
            _data_result = {}
            _subset_df = sheet_df.iloc[14:23]  # 第15行到第23行

            for item in _subset_df[['Parameter_H', 'Value_I']].to_dict(orient='records'):
                if item['Parameter_H'] == '':
                    continue
                _data_result[item['Parameter_H']] = item['Value_I']

            return _data, _data_result, sheet_df
