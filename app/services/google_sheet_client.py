import os
import time
import traceback
from typing import Optional

import gspread
from google.oauth2.credentials import Credentials
from gspread.utils import a1_to_rowcol, rowcol_to_a1
from requests.exceptions import ConnectionError, RequestException
from urllib3.exceptions import ProtocolError
from http.client import RemoteDisconnected
import functools

from gspread import Cell
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 网络连接异常类型
NETWORK_EXCEPTIONS = (
    ConnectionError,
    RequestException,
    ProtocolError,
    RemoteDisconnected
)

class GoogleSheet:
    """Google Sheet客户端类"""

    def __init__(self, spreadsheet_id, sheet_name=None, token_file="data/token.json", proxy_url=None, task_id: Optional[str] = None):
        """
        初始化Google Sheet连接

        Args:
            spreadsheet_id: 电子表格ID
            sheet_name: 工作表名称，如果不提供则不会选择具体工作表
            token_file: 认证文件路径
            proxy_url: 代理URL
        """
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        self.client = None
        self.sheet = None
        self.spreadsheet_id = spreadsheet_id
        self.title = None
        self.worksheet = None
        self.task_id = task_id
        self._last_reconnect_exception = None
        # 保存初始化参数，用于重新连接
        self._sheet_name = sheet_name
        self._token_file = token_file
        self._proxy_url = proxy_url
        self._SCOPES = SCOPES

        try:
            self._connect_and_select_worksheet()
        except Exception as e:
            logger.error(
                f"{self._log_ctx()}初始化Google Sheet连接失败: {str(e)}\n"
                f"连接参数 - Spreadsheet ID: {self.spreadsheet_id}, Sheet: {self._sheet_name}, Token: {self._token_file}"
            )
            raise

    def _connect_and_select_worksheet(self):
        creds = Credentials.from_authorized_user_file(self._token_file, scopes=self._SCOPES)
        self.client = gspread.authorize(credentials=creds)

        if self._proxy_url is not None and str(self._proxy_url).lower().startswith(('http','stock')):
            logger.info(f"{self._log_ctx()}使用代理：{self._proxy_url}")
            os.environ['HTTP_PROXY'] = self._proxy_url
            os.environ['HTTPS_PROXY'] = self._proxy_url
            self.client.session.proxies.update({"http": self._proxy_url, "https": self._proxy_url})

        self._apply_default_timeout()
        self.sheet = self.client.open_by_key(self.spreadsheet_id)
        self.title = self.sheet.title

        if not self._sheet_name:
            return

        try:
            self.worksheet = self.sheet.worksheet(self._sheet_name)
            return
        except Exception:
            try:
                worksheets = self.sheet.worksheets()
                titles = [ws.title for ws in worksheets]
            except Exception:
                titles = []

            target_lower = str(self._sheet_name).strip().lower()
            matched_title = None
            for t in titles:
                if str(t).strip().lower() == target_lower:
                    matched_title = t
                    break

            if matched_title:
                self.worksheet = self.sheet.worksheet(matched_title)
                self._sheet_name = matched_title
                return

            raise Exception(f"请先选择工作表: '{self._sheet_name}' 不存在，可用工作表: {titles}")

    def _log_ctx(self) -> str:
        parts = []
        if self.task_id:
            parts.append(f"task_id={self.task_id}")
        if self.spreadsheet_id:
            parts.append(f"spreadsheet_id={self.spreadsheet_id}")
        if self._sheet_name:
            parts.append(f"sheet_name={self._sheet_name}")
        return f"[{' '.join(parts)}] " if parts else ""

    def _apply_default_timeout(self, timeout: Optional[int] = None):
        """为 gspread 底层 requests Session 注入默认 timeout，避免网络抖动时永久阻塞"""
        if not self.client or not getattr(self.client, 'session', None):
            return

        if timeout is None:
            try:
                from app.services.config_manager import get_config_manager
                config_manager = get_config_manager()
                timeout = int(config_manager.get_config('google_sheet_http_timeout', 30))
            except Exception:
                timeout = 30

        session = self.client.session

        # 已经打过补丁：如果 timeout 发生变化，更新即可
        if getattr(session, '_timeout_patched', False):
            session._default_timeout = timeout
            return

        original_request = session.request

        @functools.wraps(original_request)
        def request_with_timeout(method, url, **kwargs):
            kwargs.setdefault('timeout', getattr(session, '_default_timeout', timeout))
            return original_request(method, url, **kwargs)

        session._default_timeout = timeout
        session.request = request_with_timeout
        session._timeout_patched = True

    def get(self, name):
        """获取属性"""
        return getattr(self, name)

    def get_row(self, row):
        """获取指定行的值"""
        return self.worksheet.row_values(row)

    def get_last_row(self, col_letter):
        """获取指定列的最后非空行"""
        try:
            col_data = self.worksheet.col_values(
                ord(col_letter) - ord('A') + 1)  # 字母转数字列号
            return len(col_data) if col_data else 0
        except Exception as e:
            logger.error(f'获取最后非空行错误。错误内容：{str(e)}')
            return -1

    def clear_range(self, range_a1: str):
        """清空一个 A1 区间，比如 'A2:A1000'（带网络重试）"""
        self._ensure_worksheet()

        if not range_a1:
            return
        logger.info(f"{self._log_ctx()}清空区间: {range_a1}")

        def _clear_operation():
            self.worksheet.batch_clear([range_a1])

        self._retry_network_operation(_clear_operation, f"clear_range({range_a1})")

    @staticmethod
    def col_letter_to_num(col_letter):
        """将Excel列字母转换为数字"""
        num = 0
        for c in col_letter:
            num = num * 26 + (ord(c) - ord('A') + 1)
        return num

    @staticmethod
    def num_to_col_letter(num):
        """将数字转换为Excel列字母"""
        if num <= 0:
            return ""
        result = ""
        while num > 0:
            num -= 1  # Adjust for 1-based indexing
            result = chr(num % 26 + ord('A')) + result
            num //= 26
        return result

    def calculate_stock_column(self, start_cell, stock_index, is_number=False):
        """
        动态计算股票在表格中的列位置

        Args:
            start_cell: 起始单元格，例如'I1'
            stock_index: 股票序号（从1开始）
            is_number: 是否返回数字格式

        Returns:
            (当前股票列, 后一列) 例如 ('M1', 'N1')
        """
        # 解析起始单元格
        start_col_letter = ''.join(filter(str.isalpha, start_cell))
        start_row = ''.join(filter(str.isdigit, start_cell))

        # 起始列号（I=9）
        start_col_num = self.col_letter_to_num(start_col_letter)

        # 第一支股票从M列开始（M=13）
        # 计算M列相对于起始列的偏移量
        base_col_offset = 13 - start_col_num

        # 计算当前股票应该在的列号
        # 第一支股票在M列，第二支在V列，第三支在AE列，间隔9列
        current_col_num = start_col_num + base_col_offset + (stock_index - 1) * 9
        current_col_letter = self.num_to_col_letter(current_col_num)

        # 计算后一列
        next_col_num = current_col_num + 1
        next_col_letter = self.num_to_col_letter(next_col_num)

        if is_number:
            return current_col_num, next_col_num
        return f"{current_col_letter}{start_row}", f"{next_col_letter}{start_row}"

    def update_row(self, sheet_row, sheet_value):
        """更新单行数据"""
        try:
            logger.info(f"{self._log_ctx()}写入：sheet_rows：{sheet_row}, sheet_values：{sheet_value}")
            self.worksheet.update(sheet_row, [[sheet_value]], value_input_option="USER_ENTERED")
        except Exception as e:
            logger.error(f'设置表格{sheet_row},值:{sheet_value}错误。错误内容：{str(e)}')
            return f'设置表格{sheet_row},值:{sheet_value}错误。错误内容：{str(e)}'

    def clear_row(self, sheet_rows):
        """清除指定行"""
        self.worksheet.range(sheet_rows).clear()

    def update_rows(self, sheet_rows, sheet_values):
        """批量更新行数据"""
        try:
            logger.info(f"{self._log_ctx()}批量写入：sheet_rows：{sheet_rows}, sheet_values：{sheet_values}")
            self.worksheet.update(sheet_rows, sheet_values, value_input_option="USER_ENTERED")
        except Exception as e:
            logger.error(f'设置表格{sheet_rows},值:{sheet_values}错误。错误内容：{str(e)}')
            return f'设置表格{sheet_rows},值:{sheet_values}错误。错误内容：{str(e)}'

    def update_cell(self, cell_address, cell_value):
        """更新单个单元格"""
        try:
            # 验证输入参数
            if not cell_address:
                raise ValueError("单元格地址不能为空")

            # 确保cell_value是可序列化的值
            if cell_value is None:
                cell_value = ""
            elif isinstance(cell_value, (int, float, str, bool)):
                # 这些类型是安全的
                pass
            else:
                # 其他类型转换为字符串
                cell_value = str(cell_value)

            logger.info(f"{self._log_ctx()}更新单元格 {cell_address} = {cell_value} (类型: {type(cell_value)})")

            def _update_operation():
                self.worksheet.update(cell_address, cell_value)

            self._retry_network_operation(_update_operation, f"update_cell({cell_address})")

        except Exception as e:
            error_msg = f"{self._log_ctx()}更新单元格 {cell_address} 失败，值: {cell_value}, 错误: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    def update_jumped_cells(self, cell_updates):
        """
        更新跳跃的单元格（带网络重试）

        Args:
            cell_updates: 字典，格式为 {单元格地址: 新值}
            例如: {"A1": "姓名", "I1": "年龄", "N1": "城市", "AI1": "职业"}
        """
        self._ensure_worksheet()

        # 检查cell_updates是否为空
        if not cell_updates:
            logger.warning(f"{self._log_ctx()}cell_updates为空，跳过更新操作")
            return None

        try:
            # 创建Cell对象列表
            cells = []
            for cell_address, value in cell_updates.items():
                # 验证单元格地址格式
                if not cell_address or not isinstance(cell_address, str):
                    logger.warning(f"{self._log_ctx()}无效的单元格地址: {cell_address}")
                    continue

                # 将A1表示法转换为行列号
                row, col = gspread.utils.a1_to_rowcol(cell_address)
                cells.append(Cell(row, col, value))

            # 如果没有有效的单元格，直接返回
            if not cells:
                logger.warning(f"{self._log_ctx()}没有有效的单元格需要更新")
                return None

            # 批量更新单元格（带重试）
            def _update_operation():
                return self.worksheet.update_cells(cells)

            return self._retry_network_operation(_update_operation, "update_jumped_cells")

        except Exception as e:
            logger.error(f"{self._log_ctx()}更新跳跃单元格失败: {e}", exc_info=True)
            raise  # 重试后仍失败则抛出异常

    def get_cell(self, cell_ref):
        """获取指定单元格的值"""

        def _get_cell_operation():
            return self.worksheet.get(cell_ref)[0][0]

        return self._retry_network_operation(_get_cell_operation, f"get_cell({cell_ref})")

    def get_range(self, range_a1: str, value_render_option: str = 'FORMATTED_VALUE'):
        """根据 A1 区间获取整块区域的值，返回 {单元格A1: 值} 字典（带网络重试）

        value_render_option:
            - 'FORMATTED_VALUE'  默认，返回表格里看到的格式化结果（如 '71.88%')
            - 'UNFORMATTED_VALUE' 返回底层原始数值（如 0.718870846209405）
            - 'FORMULA'           返回公式本身（如 '=...'）
        """
        self._ensure_worksheet()

        if not range_a1:
            return {}

        def _get_range_operation():
            values_2d = self.worksheet.get(range_a1, value_render_option=value_render_option)
            start_row, start_col = a1_to_rowcol(range_a1.split(':')[0])
            result = {}
            for r_idx, row in enumerate(values_2d):
                for c_idx, value in enumerate(row):
                    row_num = start_row + r_idx
                    col_num = start_col + c_idx
                    cell_a1 = rowcol_to_a1(row_num, col_num)
                    result[cell_a1] = value
            return result

        return self._retry_network_operation(_get_range_operation, f"get_range({range_a1})")


    def get_range_2d(self, range_a1: str, value_render_option: str = 'FORMATTED_VALUE'):
        """根据 A1 区间获取整块区域的值，

        value_render_option:
            - 'FORMATTED_VALUE'  默认，返回表格里看到的格式化结果（如 '71.88%')
            - 'UNFORMATTED_VALUE' 返回底层原始数值（如 0.718870846209405）
            - 'FORMULA'           返回公式本身（如 '=...'）
        """
        self._ensure_worksheet()

        if not range_a1:
            return {}

        def _get_range_operation():
            values_2d = self.worksheet.get(range_a1, value_render_option=value_render_option)
            return values_2d

        return self._retry_network_operation(_get_range_operation, f"get_range({range_a1})")


    def get_cells_batch(self, cell_refs):
        """
        批量获取多个单元格的值

        Args:
            cell_refs: 单元格引用列表，例如 ['A1', 'B2', 'C3']

        Returns:
            字典，格式为 {单元格地址: 值}
        """
        self._ensure_worksheet()

        if not cell_refs:
            logger.warning(f"{self._log_ctx()}cell_refs为空，返回空字典")
            return {}

        try:
            def _batch_get_operation():
                ranges = [f"{ref}" for ref in cell_refs]
                return self.worksheet.batch_get(ranges)

            batch_values = self._retry_network_operation(_batch_get_operation, "get_cells_batch")

            results = {}
            for i, cell_ref in enumerate(cell_refs):
                if i < len(batch_values) and batch_values[i]:
                    value = batch_values[i][0][0] if batch_values[i][0] else ""
                    results[cell_ref] = value
                else:
                    results[cell_ref] = ""

            return results

        except Exception as e:
            logger.error(f"{self._log_ctx()}批量获取单元格失败: {e}", exc_info=True)
            logger.info(f"{self._log_ctx()}回退到逐个获取单元格值")
            results = {}
            for cell_ref in cell_refs:
                try:
                    value = self.get_cell(cell_ref)
                    results[cell_ref] = value
                except Exception as cell_error:
                    logger.error(f"{self._log_ctx()}获取单元格 {cell_ref} 失败: {cell_error}")
                    results[cell_ref] = ""
            return results

    def get_trade_count_with_retry(self, cell_ref, max_retries=None, delay=None):
        """带重试机制获取交易数量"""
        # 从配置获取重试参数
        from app.services.config_manager import get_config_manager
        config_manager = get_config_manager()
        if max_retries is None:
            max_retries = config_manager.get_config('api_retry_max_attempts', 10)
        if delay is None:
            delay = config_manager.get_config('api_retry_delay', 30)
            
        retry_count = 0
        while retry_count < max_retries:
            try:
                trade_count = self.get_cell(cell_ref)
                if trade_count != '#DIV/0!' and trade_count.find("target") == -1:
                    return trade_count
            except Exception as e:
                logger.error(f'{self._log_ctx()}获取交易数量出错: {str(e)}')
            logger.info(f'{self._log_ctx()}重试中，已尝试{retry_count}次')
            retry_count += 1
            if retry_count < max_retries:
                time.sleep(delay)
        logger.warning(f'{self._log_ctx()}多次尝试后，仍无法获取有效的交易数量，返回0')
        return '0'

    def get_all_worksheets(self):
        """获取电子表格中的所有工作表名称"""
        try:
            if not self.sheet:
                raise ValueError("未初始化Google Sheet连接")
            worksheets = self.sheet.worksheets()
            return [ws.title for ws in worksheets]
        except Exception as e:
            logger.error(f'{self._log_ctx()}获取工作表列表失败: {str(e)}')
            raise

    def _reconnect(self):
        """
        重新连接Google Sheet（用于网络连接中断后恢复）
        """
        try:
            self._last_reconnect_exception = None
            logger.info(f"{self._log_ctx()}尝试重新连接Google Sheet")
            # 先关闭旧连接
            self.close()
            # 重新加载凭证
            creds = Credentials.from_authorized_user_file(self._token_file, scopes=self._SCOPES)
            self.client = gspread.authorize(credentials=creds)

            if self._proxy_url:
                logger.info(f"{self._log_ctx()}使用代理：{self._proxy_url}")
                os.environ['HTTP_PROXY'] = self._proxy_url
                os.environ['HTTPS_PROXY'] = self._proxy_url
                self.client.session.proxies.update({"http": self._proxy_url, "https": self._proxy_url})

            self._apply_default_timeout()
            # 重新打开电子表格
            self.sheet = self.client.open_by_key(self.spreadsheet_id)
            self.title = self.sheet.title

            # 重新选择工作表
            if self._sheet_name:
                try:
                    self.worksheet = self.sheet.worksheet(self._sheet_name)
                except Exception:
                    worksheets = self.sheet.worksheets()
                    titles = [ws.title for ws in worksheets]
                    target_lower = str(self._sheet_name).strip().lower()
                    matched_title = None
                    for t in titles:
                        if str(t).strip().lower() == target_lower:
                            matched_title = t
                            break
                    if matched_title:
                        self.worksheet = self.sheet.worksheet(matched_title)
                        self._sheet_name = matched_title
                    else:
                        raise Exception(f"请先选择工作表: '{self._sheet_name}' 不存在，可用工作表: {titles}")
            logger.info(f"{self._log_ctx()}Google Sheet重新连接成功")
            return True
        except Exception as e:
            self._last_reconnect_exception = e
            logger.error(f"{self._log_ctx()}重新连接Google Sheet失败: {str(e)}")
            return False

    def _is_network_error(self, exception):
        """判断是否是网络连接错误"""
        # 检查异常类型
        try:
            from gspread.exceptions import APIError as _GSAPIError
            if isinstance(exception, _GSAPIError):
                resp = getattr(exception, 'response', None)
                status = getattr(resp, 'status_code', None)
                if isinstance(status, int) and (status >= 500 or status == 429):
                    return True
        except Exception:
            pass

        # 检查错误消息关键词（用于捕获 gspread 包装的网络错误）
        error_str = str(exception).lower()
        network_keywords = [
            'connection', 'disconnected', 'aborted', 'remote end',
            'protocol error', 'network', 'timeout', 'broken pipe',
            ' 500', ' 502', ' 503', ' 504', ' 429'
        ]
        return any(keyword in error_str for keyword in network_keywords)
        
    def _ensure_worksheet(self):
        """确保 worksheet 已可用；为空时尝试重连并重新选择工作表"""
        if not self.worksheet:
            if not self._reconnect():
                # 关键：重连失败时抛出原始异常，让上层按网络错误重试/退出
                if self._last_reconnect_exception is not None:
                    raise self._last_reconnect_exception
                raise Exception("请先选择工作表")

    def _retry_network_operation(self, operation, operation_name, max_retries=3, delay=2, reconnect_on_error=True):
        """
        带重试机制执行网络操作
        
        Args:
            operation: 要执行的操作函数（无参数）
            operation_name: 操作名称（用于日志）
            max_retries: 最大重试次数
            delay: 重试延迟（秒），会指数递增
            reconnect_on_error: 是否在错误时重新连接
        
        Returns:
            操作结果
        """
        last_exception = None
        for attempt in range(max_retries):
            try:
                self._ensure_worksheet()
                return operation()
            except Exception as e:
                # 判断是否是网络错误
                if not self._is_network_error(e):
                    # 不是网络错误，直接抛出
                    raise
                
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)  # 指数退避
                    logger.warning(
                        f"{operation_name} 网络错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}. "
                        f"{wait_time}秒后重试..."
                    )
                    
                    # 如果需要重新连接
                    if reconnect_on_error:
                        self._reconnect()
                    
                    time.sleep(wait_time)
                else:
                    logger.error(f"{operation_name} 网络错误，已重试 {max_retries} 次仍失败: {str(e)}")
                    raise
        
        # 如果所有重试都失败了
        if last_exception:
            raise last_exception

    def close(self):
        """关闭连接并清理资源"""
        try:
            # 清理代理设置
            if 'HTTP_PROXY' in os.environ:
                del os.environ['HTTP_PROXY']
            if 'HTTPS_PROXY' in os.environ:
                del os.environ['HTTPS_PROXY']
            
            # 清理对象引用
            self.worksheet = None
            self.sheet = None
            if self.client:
                try:
                    self.client.session.close()  # 关闭gspread的session
                except:
                    pass
            self.client = None
            
        except Exception as e:
            logger.warning(f"关闭Google Sheet连接时出错: {str(e)}")
            
    def __enter__(self):
        """上下文管理器入口"""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()


if __name__ == '__main__':
    with GoogleSheet('17pocRAANadKiJs-Z4lujPxj0em_1Gkdt8CW6l04tvrc','control',token_file=r'D:\Users\Administrator\Desktop\谷歌参数批量校验\data\token.json') as sheet:
        print(sheet.get_range("L2:L100"))