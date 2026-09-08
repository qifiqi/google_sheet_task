"""远程数据服务（DY.Stock.Api）的统一 HTTP 接入点。

Repository 只能通过本模块调用远程接口。本模块自带轻量传输层，负责:

- 端点注册表解析（``(group, operation) -> HTTP 方法 + 路径``）;
- 集中配置读取（``STOCK_BASE_URL`` / ``STOCK_API_TIMEOUT`` /
  ``STOCK_API_TOKEN``）与 ``Token`` 请求头注入;
- 统一响应信封（``ret_code / ret_msg / ret_count / ret_obj``）解包;
- 传输异常到本模块异常体系的翻译，避免 requests 细节扩散到服务层。

用户 Token 只能通过 ``Token`` 请求头传递（如身份校验接口），而客户端
凭据在构造时绑定，因此这里按 Token 缓存独立客户端，避免每个请求都
重建连接池，也避免与服务级 ``STOCK_API_TOKEN`` 的全局客户端互相干扰。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from typing import Any

import requests


logger = logging.getLogger(__name__)


class SdkDataAccessError(RuntimeError):
    """Repository 与远程数据服务交互时的基础异常。"""


class SdkConfigurationError(SdkDataAccessError):
    """远程数据服务缺少必要配置时抛出。"""


class SdkProtocolError(SdkDataAccessError):
    """远程响应不符合统一信封约定时抛出。"""


class SdkOperationError(SdkDataAccessError):
    """远程服务已接收请求但业务校验失败时抛出。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        """保存远程业务错误消息及可选错误码。"""
        super().__init__(message)
        self.code = code


class SdkDuplicateKeyError(SdkOperationError):
    """远程唯一约束冲突；调用方必须避免覆盖既有记录。"""


class SdkNotFoundError(SdkOperationError):
    """远程服务明确返回记录不存在时抛出。"""


class SdkFilterUnavailableError(SdkDataAccessError):
    """远程服务未声明所需业务筛选能力时抛出。"""


# 远程接口注册表: (group, operation) -> (HTTP 方法, 路径)。
# 路径与远程 Swagger 控制器一一对应；新增远程接口时在此登记，
# Repository 仍通过 ``StockSdkAdapter.call(group, operation, payload)`` 调用。
_REMOTE_ENDPOINTS: dict[tuple[str, str], tuple[str, str]] = {
    ("param_backtest_product_result_cache", "delete"): ("POST", "/api/ParamBacktestProductResultCache/Delete"),
    ("param_backtest_product_result_cache", "get_data_by_page_list"): ("POST", "/api/ParamBacktestProductResultCache/GetDataByPageList"),
    ("param_backtest_product_result_cache", "get_info_by_id"): ("POST", "/api/ParamBacktestProductResultCache/GetInfoById"),
    ("param_backtest_product_result_cache", "modify_or_add"): ("POST", "/api/ParamBacktestProductResultCache/ModifyOrAdd"),
    ("param_backtest_sheet_run_locks", "delete"): ("POST", "/api/ParamBacktestSheetRunLocks/Delete"),
    ("param_backtest_sheet_run_locks", "get_data_by_page_list"): ("POST", "/api/ParamBacktestSheetRunLocks/GetDataByPageList"),
    ("param_backtest_sheet_run_locks", "get_info_by_id"): ("POST", "/api/ParamBacktestSheetRunLocks/GetInfoById"),
    ("param_backtest_sheet_run_locks", "modify_or_add"): ("POST", "/api/ParamBacktestSheetRunLocks/ModifyOrAdd"),
    ("param_google_sheet", "delete"): ("POST", "/api/ParamGoogleSheet/Delete"),
    ("param_google_sheet", "get_data_by_page_list"): ("POST", "/api/ParamGoogleSheet/GetDataByPageList"),
    ("param_google_sheet", "get_info_by_id"): ("POST", "/api/ParamGoogleSheet/GetInfoById"),
    ("param_google_sheet", "modify_or_add"): ("POST", "/api/ParamGoogleSheet/ModifyOrAdd"),
    ("param_google_sheet_tokens", "delete"): ("POST", "/api/ParamGoogleSheetTokens/Delete"),
    ("param_google_sheet_tokens", "get_data_by_page_list"): ("POST", "/api/ParamGoogleSheetTokens/GetDataByPageList"),
    ("param_google_sheet_tokens", "get_info_by_id"): ("POST", "/api/ParamGoogleSheetTokens/GetInfoById"),
    ("param_google_sheet_tokens", "modify_or_add"): ("POST", "/api/ParamGoogleSheetTokens/ModifyOrAdd"),
    ("param_scheduled_tasks", "delete"): ("POST", "/api/ParamScheduledTasks/Delete"),
    ("param_scheduled_tasks", "get_data_by_page_list"): ("POST", "/api/ParamScheduledTasks/GetDataByPageList"),
    ("param_scheduled_tasks", "get_info_by_id"): ("POST", "/api/ParamScheduledTasks/GetInfoById"),
    ("param_scheduled_tasks", "modify_or_add"): ("POST", "/api/ParamScheduledTasks/ModifyOrAdd"),
    ("param_stock_metadata", "delete"): ("POST", "/api/ParamStockMetadata/Delete"),
    ("param_stock_metadata", "get_data_by_page_list"): ("POST", "/api/ParamStockMetadata/GetDataByPageList"),
    ("param_stock_metadata", "get_info_by_id"): ("POST", "/api/ParamStockMetadata/GetInfoById"),
    ("param_stock_metadata", "modify_or_add"): ("POST", "/api/ParamStockMetadata/ModifyOrAdd"),
    ("param_system_configs", "delete"): ("POST", "/api/ParamSystemConfigs/Delete"),
    ("param_system_configs", "get_data_by_page_list"): ("POST", "/api/ParamSystemConfigs/GetDataByPageList"),
    ("param_system_configs", "get_info_by_id"): ("POST", "/api/ParamSystemConfigs/GetInfoById"),
    ("param_system_configs", "modify_or_add"): ("POST", "/api/ParamSystemConfigs/ModifyOrAdd"),
    ("param_task_logs", "delete"): ("POST", "/api/ParamTaskLogs/Delete"),
    ("param_task_logs", "get_data_by_page_list"): ("POST", "/api/ParamTaskLogs/GetDataByPageList"),
    ("param_task_logs", "get_info_by_id"): ("POST", "/api/ParamTaskLogs/GetInfoById"),
    ("param_task_logs", "modify_or_add"): ("POST", "/api/ParamTaskLogs/ModifyOrAdd"),
    ("param_task_result_summary_index", "delete"): ("POST", "/api/ParamTaskResultSummaryIndex/Delete"),
    ("param_task_result_summary_index", "get_data_by_page_list"): ("POST", "/api/ParamTaskResultSummaryIndex/GetDataByPageList"),
    ("param_task_result_summary_index", "get_data_summary"): ("POST", "/api/ParamTaskResultSummaryIndex/GetDataSummary"),
    ("param_task_result_summary_index", "get_info_by_id"): ("POST", "/api/ParamTaskResultSummaryIndex/GetInfoById"),
    ("param_task_result_summary_index", "modify_or_add"): ("POST", "/api/ParamTaskResultSummaryIndex/ModifyOrAdd"),
    ("param_task_results", "delete"): ("POST", "/api/ParamTaskResults/Delete"),
    ("param_task_results", "get_data_by_page_list"): ("POST", "/api/ParamTaskResults/GetDataByPageList"),
    ("param_task_results", "get_info_by_id"): ("POST", "/api/ParamTaskResults/GetInfoById"),
    ("param_task_results", "modify_or_add"): ("POST", "/api/ParamTaskResults/ModifyOrAdd"),
    ("param_task_results_return", "delete"): ("POST", "/api/ParamTaskResultsReturn/Delete"),
    ("param_task_results_return", "get_data_by_page_list"): ("POST", "/api/ParamTaskResultsReturn/GetDataByPageList"),
    ("param_task_results_return", "get_info_by_id"): ("POST", "/api/ParamTaskResultsReturn/GetInfoById"),
    ("param_task_results_return", "modify_or_add"): ("POST", "/api/ParamTaskResultsReturn/ModifyOrAdd"),
    ("param_task_templates", "delete"): ("POST", "/api/ParamTaskTemplates/Delete"),
    ("param_task_templates", "get_data_by_page_list"): ("POST", "/api/ParamTaskTemplates/GetDataByPageList"),
    ("param_task_templates", "get_info_by_id"): ("POST", "/api/ParamTaskTemplates/GetInfoById"),
    ("param_task_templates", "modify_or_add"): ("POST", "/api/ParamTaskTemplates/ModifyOrAdd"),
    ("param_tasks", "delete"): ("POST", "/api/ParamTasks/Delete"),
    ("param_tasks", "get_data_by_page_list"): ("POST", "/api/ParamTasks/GetDataByPageList"),
    ("param_tasks", "get_info_by_id"): ("POST", "/api/ParamTasks/GetInfoById"),
    ("param_tasks", "modify_or_add"): ("POST", "/api/ParamTasks/ModifyOrAdd"),
    ("stock_data", "delete"): ("POST", "/api/StockData/Delete"),
    ("stock_data", "get_by_id"): ("POST", "/api/StockData/GetById"),
    ("stock_data", "get_data_all_list"): ("POST", "/api/StockData/GetDataAllList"),
    ("stock_data", "get_data_by_page_list"): ("POST", "/api/StockData/GetDataByPageList"),
    ("stock_data", "get_list_his_page"): ("POST", "/api/StockData/GetListHisPage"),
    ("stock_data", "get_list_page"): ("POST", "/api/StockData/GetListPage"),
    ("stock_data", "get_list_volume"): ("POST", "/api/StockData/GetListVolume"),
    ("stock_data", "get_stock_list_by_code"): ("POST", "/api/StockData/GetStockListByCode"),
    ("stock_data", "get_stock_list_by_code_or_date"): ("POST", "/api/StockData/GetStockListByCodeOrDate"),
    ("stock_data", "modify_or_add"): ("POST", "/api/StockData/ModifyOrAdd"),
    ("stock_data_us", "delete"): ("POST", "/api/StockDataUs/Delete"),
    ("stock_data_us", "get_by_id"): ("POST", "/api/StockDataUs/GetById"),
    ("stock_data_us", "get_data_all_list"): ("POST", "/api/StockDataUs/GetDataAllList"),
    ("stock_data_us", "get_data_by_page_list"): ("POST", "/api/StockDataUs/GetDataByPageList"),
    ("stock_data_us", "get_list_his_page"): ("POST", "/api/StockDataUs/GetListHisPage"),
    ("stock_data_us", "get_list_page"): ("POST", "/api/StockDataUs/GetListPage"),
    ("stock_data_us", "modify_or_add"): ("POST", "/api/StockDataUs/ModifyOrAdd"),
    ("sys_model", "delete"): ("POST", "/api/SysModel/Delete"),
    ("sys_model", "get_by_id"): ("POST", "/api/SysModel/GetById"),
    ("sys_model", "get_data_by_page_list"): ("POST", "/api/SysModel/GetDataByPageList"),
    ("sys_model", "get_top_model_list"): ("POST", "/api/SysModel/GetTopModelList"),
    ("sys_model", "modify_or_add"): ("POST", "/api/SysModel/ModifyOrAdd"),
    ("sys_user", "get"): ("POST", "/api/SysUser/Get"),
    ("sys_user", "get_by_id"): ("POST", "/api/SysUser/GetById"),
    ("sys_user", "get_data_by_page_list"): ("POST", "/api/SysUser/GetDataByPageList"),
    ("sys_user", "get_list_for_select"): ("POST", "/api/SysUser/GetListForSelect"),
    ("sys_user", "get_user_info"): ("POST", "/api/SysUser/GetUserInfo"),
    ("sys_user", "get_user_role_list"): ("POST", "/api/SysUser/GetUserRoleList"),
    ("sys_user", "login"): ("POST", "/api/SysUser/Login"),
    ("sys_user", "pwd_reset"): ("POST", "/api/SysUser/PwdReset"),
    ("sys_user", "register"): ("POST", "/api/SysUser/Register"),
    ("sys_user", "update_pwd"): ("POST", "/api/SysUser/UpdatePwd"),
    ("sys_user", "update_user_role"): ("POST", "/api/SysUser/UpdateUserRole"),
    ("sys_user", "user_enable_or_un_enable"): ("POST", "/api/SysUser/UserEnableOrUnEnable"),
}


class RemoteHttpClient:
    """面向 DY.Stock.Api 的极薄同步 HTTP 客户端。

    实例在构造时绑定 ``Token`` 请求头凭据与超时配置；服务级调用传入
    ``token=None``（凭据回退 ``STOCK_API_TOKEN``），用户身份调用传入
    登录颁发的用户 Token。
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str,
        timeout: float,
    ) -> None:
        """绑定凭据与目标地址；网络会话在实例内复用。"""
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """发送一次请求并返回统一响应信封字典。

        与主 Web 前端 ``$.ajaxs`` 的契约一致：请求体恒为 JSON 编码的
        ``payload``，空载荷也发送 ``{}`` 并携带 ``Content-Type:
        application/json``——远端 ``[FromBody]`` 接口在请求体缺失或
        Content-Type 不符时返回 HTTP 415。传输错误与 HTTP 错误翻译为
        本模块异常。
        """
        headers: dict[str, str] = {}
        if self.token:
            headers["Token"] = self.token
        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                json=dict(payload or {}),
                headers=headers,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise SdkDataAccessError(f"远程数据服务请求超时: {path}") from exc
        except requests.RequestException as exc:
            raise SdkDataAccessError(f"远程数据服务连接失败: {exc}") from exc
        if response.status_code >= 400:
            # 错误响应不保证是 JSON；无论返回 JSON、纯文本还是 HTML，
            # 都保留原始内容交给日志记录，避免丢失服务端错误原因。
            try:
                detail = response.json() if response.content else ""
            except ValueError:
                detail = response.text
            raise SdkDataAccessError(
                f"远程数据服务 HTTP {response.status_code}: {detail}"
            )
        if not response.content:
            raise SdkProtocolError("远程数据服务返回空响应体")
        try:
            envelope = response.json()
        except ValueError as exc:
            raise SdkProtocolError("远程数据服务响应不是 JSON") from exc
        if not isinstance(envelope, dict):
            raise SdkProtocolError("远程响应不符合统一信封约定")
        return envelope


class StockSdkAdapter:
    """调用远程接口，并向上层只返回解包后的 ``ret_obj``。"""

    # 按 Token 缓存的客户端数量上限；超限时整体清空，身份调用频率低，
    # 重建成本可接受。
    _MAX_CACHED_CLIENTS = 64

    def __init__(self) -> None:
        """服务级与各用户 Token 的客户端按需创建并缓存。"""
        self._clients: dict[str | None, RemoteHttpClient] = {}
        self._clients_lock = threading.Lock()

    @staticmethod
    def _get_setting(name: str, default: Any = None) -> Any:
        """优先从 Flask 配置读取；离线场景才回退到环境变量。"""
        try:
            from flask import current_app, has_app_context

            if has_app_context():
                return current_app.config.get(name, default)
        except RuntimeError:
            pass
        return os.environ.get(name, default)

    @classmethod
    def _build_client(cls, token: str | None = None) -> RemoteHttpClient:
        """根据集中配置构造 HTTP 客户端，避免业务代码自行读取环境变量。"""
        base_url = str(cls._get_setting("STOCK_BASE_URL", "") or "").strip()
        if not base_url:
            raise SdkConfigurationError(
                "STOCK_BASE_URL 未配置，无法使用远程数据访问服务"
            )
        try:
            timeout = float(cls._get_setting("STOCK_API_TIMEOUT", 10.0))
        except (TypeError, ValueError) as exc:
            raise SdkConfigurationError("STOCK_API_TIMEOUT 必须是正数") from exc
        if timeout <= 0:
            raise SdkConfigurationError("STOCK_API_TIMEOUT 必须大于 0")
        resolved_token = str(
            token or cls._get_setting("STOCK_API_TOKEN", "") or ""
        ).strip()
        return RemoteHttpClient(
            token=resolved_token or None,
            base_url=base_url,
            timeout=timeout,
        )

    def _client_for(self, token: str | None) -> RemoteHttpClient:
        """取该 Token 对应的 HTTP 客户端，缺失时按集中配置创建。"""
        cached = self._clients.get(token)
        if cached is not None:
            return cached
        with self._clients_lock:
            client = self._clients.get(token)
            if client is not None:
                return client
            if len(self._clients) >= self._MAX_CACHED_CLIENTS:
                self._clients.clear()
            client = self._build_client(token)
            self._clients[token] = client
            return client

    @staticmethod
    def _safe_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        """脱敏后返回请求载荷，供详细日志使用。"""
        sensitive_names = (
            "token",
            "password",
            "secret",
            "authorization",
            "credential",
            "cookie",
        )

        def sanitize(value: Any, key: str = "") -> Any:
            if any(name in key.lower() for name in sensitive_names):
                return "***"
            if isinstance(value, Mapping):
                return {str(item_key): sanitize(item_value, str(item_key)) for item_key, item_value in value.items()}
            if isinstance(value, (list, tuple)):
                return [sanitize(item) for item in value]
            return value

        return sanitize(payload)

    def call(
        self,
        group_name: str,
        operation: str,
        payload: Mapping[str, Any],
        *,
        token: str | None = None,
    ) -> Any:
        """调用一个远程接口，并仅返回解包后的 ``ret_obj``。

        ``token`` 用于身份校验等按用户上下文调用的场景：远程接口从
        ``Token`` 请求头读取凭据。远程传输错误和业务失败会转换为本模块
        定义的异常，防止服务层依赖 HTTP 实现细节。
        """
        endpoint = _REMOTE_ENDPOINTS.get((group_name, operation))
        if endpoint is None:
            raise SdkProtocolError(f"未注册的远程接口: {group_name}.{operation}")
        method, path = endpoint
        body = dict(payload or {})
        client = self._client_for(token)

        # 所有 Repository 的远程 HTTP 请求都汇集到这里；仅记录字段名，
        # 避免日志泄漏 Token、收益序列及任务参数等可能很大的敏感请求内容。
        logger.info(
            "SDK HTTP 调用开始: group=%s operation=%s payload_fields=%s",
            group_name,
            operation,
            ",".join(sorted(str(key) for key in body)),
        )
        try:
            envelope = client.request(method, path, body)
        except SdkDataAccessError as exc:
            logger.warning(
                "远程数据接口调用失败: group=%s operation=%s error=%s "
                "message=%s request_payload=%s",
                group_name,
                operation,
                exc.__class__.__name__,
                str(exc),
                json.dumps(self._safe_payload(body), ensure_ascii=False, default=str),
                exc_info=True,
            )
            raise

        code = envelope.get("ret_code", envelope.get("retCode"))
        message = str(
            envelope.get("ret_msg", envelope.get("retMsg")) or "远程数据服务拒绝请求"
        )
        if code != 200:
            logger.warning(
                "远程数据接口返回业务失败: group=%s operation=%s code=%s",
                group_name,
                operation,
                code,
            )
            # 远端服务以 409 或稳定错误码标识唯一键冲突，供锁和幂等写入处理。
            if code == 409 or "DUPLICATE_KEY" in message.upper():
                raise SdkDuplicateKeyError(message, code=code)
            if code == 404:
                raise SdkNotFoundError(message, code=code)
            raise SdkOperationError(message, code=code)
        return envelope.get("ret_obj", envelope.get("retObj"))
