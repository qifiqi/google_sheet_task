"""DY.Stock.Api 远程接口客户端（db-to-http 数据层唯一 HTTP 出口）。

目录结构：

- ``client.py``     统一调用器 ``StockApiClient``：配置读取、按 Token 缓存
  传输实例、统一信封解包、异常翻译、出站布尔 0/1 编码与脱敏日志；
- ``base.py``       控制器基类：通用调用器 ``_make_request``；
- ``controllers/``  按 URL 中段（Swagger 控制器）拆分的接口模块，每个具体
  端点一个命名函数（docstring 含 curl 示例）；
- ``exceptions.py`` 远程访问异常体系。

Repository 与 KlineService 统一经模块级单例 ``stock_api`` 调用，例如::

    from app.remote_api import stock_api

    rows = stock_api.stock_data.get_data_all_list({"stock_code": "600000.SH"})
    stock_api.param_tasks.modify_or_add({"id": task_id, ...})

测试可注入独立 ``StockApiClient()`` 或替身对象。
"""

from app.remote_api.base import ControllerApi
from app.remote_api.client import StockApiClient, encode_remote_body
from app.remote_api.exceptions import (
    RemoteApiConfigError,
    RemoteApiDuplicateKeyError,
    RemoteApiError,
    RemoteApiNotFoundError,
    RemoteApiOperationError,
    RemoteApiProtocolError,
)

__all__ = [
    "ControllerApi",
    "StockApiClient",
    "encode_remote_body",
    "RemoteApiConfigError",
    "RemoteApiDuplicateKeyError",
    "RemoteApiError",
    "RemoteApiNotFoundError",
    "RemoteApiOperationError",
    "RemoteApiProtocolError",
    "stock_api",
]

# 模块级单例：构造只绑定控制器（传输实例按需懒建），无网络副作用。
stock_api = StockApiClient()
