"""任务线程域信号异常：Google Sheet 模板检查发现 #ERROR 类无效值。

属执行链语义（无 HTTP 语义），不并入 AppException 体系。
由 checkForErrors 改名而来（PEP8 CapWords；2026-09 审计 CLN-04）。
"""


class SheetCheckError(Exception):
    """Sheet 检查出现 #、#N/A 等无效值时的任务域信号异常。"""
