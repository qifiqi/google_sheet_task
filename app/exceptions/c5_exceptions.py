"""
C5服务专用异常类系统
提供详细的异常信息和错误分类
"""
from typing import Optional, Dict, Any


class C5BaseException(Exception):
    """C5服务基础异常类"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, 
                 error_type: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "C5_UNKNOWN_ERROR"
        self.error_type = error_type or self.__class__.__name__
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于序列化"""
        return {
            "error_code": self.error_code,
            "error_type": self.error_type,
            "message": self.message,
            "details": self.details
        }
    
    def __str__(self):
        details_str = f", details: {self.details}" if self.details else ""
        return f"[{self.error_code}] {self.message}{details_str}"


class C5NetworkException(C5BaseException):
    """网络连接异常"""
    
    def __init__(self, message: str, http_status: Optional[int] = None, 
                 request_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if http_status:
            error_details["http_status"] = http_status
        if request_id:
            error_details["request_id"] = request_id
        
        super().__init__(
            message=message,
            error_code="C5_NETWORK_ERROR",
            error_type="NetworkException",
            details=error_details
        )
        self.http_status = http_status
        self.request_id = request_id


class C5RateLimitException(C5NetworkException):
    """速率限制异常（429）"""
    
    def __init__(self, message: str = "请求频率过高，触发速率限制", 
                 retry_after: Optional[int] = None, request_id: Optional[str] = None):
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
        if request_id:
            details["request_id"] = request_id
        
        super().__init__(
            message=message,
            http_status=429,
            request_id=request_id,
            details=details
        )
        self.retry_after = retry_after


class C5ExecutionException(C5BaseException):
    """执行异常（业务逻辑错误）"""
    
    def __init__(self, message: str, step_index: Optional[int] = None,
                 parameter_info: Optional[Dict[str, Any]] = None, 
                 details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if step_index is not None:
            error_details["step_index"] = step_index
        if parameter_info:
            error_details["parameter_info"] = parameter_info
        
        super().__init__(
            message=message,
            error_code="C5_EXECUTION_ERROR",
            error_type="ExecutionException",
            details=error_details
        )
        self.step_index = step_index
        self.parameter_info = parameter_info


class C5ValidationException(C5ExecutionException):
    """验证异常（数据验证失败）"""
    
    def __init__(self, message: str, validation_errors: Optional[Dict[str, Any]] = None,
                 step_index: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if validation_errors:
            error_details["validation_errors"] = validation_errors
        
        super().__init__(
            message=message,
            step_index=step_index,
            details=error_details
        )
        self.error_code = "C5_VALIDATION_ERROR"
        self.error_type = "ValidationException"
        self.validation_errors = validation_errors


class C5TimeoutException(C5BaseException):
    """超时异常"""
    
    def __init__(self, message: str = "操作超时", timeout_seconds: Optional[float] = None,
                 details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if timeout_seconds:
            error_details["timeout_seconds"] = timeout_seconds
        
        super().__init__(
            message=message,
            error_code="C5_TIMEOUT_ERROR",
            error_type="TimeoutException",
            details=error_details
        )
        self.timeout_seconds = timeout_seconds


class C5DataException(C5BaseException):
    """数据异常（数据格式、数据缺失等）"""
    
    def __init__(self, message: str, data_info: Optional[Dict[str, Any]] = None,
                 details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if data_info:
            error_details["data_info"] = data_info
        
        super().__init__(
            message=message,
            error_code="C5_DATA_ERROR",
            error_type="DataException",
            details=error_details
        )
        self.data_info = data_info
