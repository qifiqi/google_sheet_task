"""远程数据服务（DY.Stock.Api）异常体系。

Repository / service 只依赖本模块异常，不感知 HTTP 与 requests 细节；
由 ``app/remote_api/client.py`` 的通用调用器统一完成异常翻译。
"""


class RemoteApiError(RuntimeError):
    """与远程数据服务交互时的基础异常。"""


class RemoteApiConfigError(RemoteApiError):
    """远程数据服务缺少必要配置时抛出。"""


class RemoteApiProtocolError(RemoteApiError):
    """远程响应不符合统一信封约定时抛出。"""


class RemoteApiOperationError(RemoteApiError):
    """远程服务已接收请求但业务校验失败时抛出。"""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        """保存远程业务错误消息及可选错误码。"""
        super().__init__(message)
        self.code = code


class RemoteApiDuplicateKeyError(RemoteApiOperationError):
    """远程唯一约束冲突；调用方必须避免覆盖既有记录。"""


class RemoteApiNotFoundError(RemoteApiOperationError):
    """远程服务明确返回记录不存在时抛出。"""
