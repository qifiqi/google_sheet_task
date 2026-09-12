"""请求边界 Schema（Pydantic v2）。

纪律（docs/design/api-model-query-audit/05 §2.4）：
- 只做请求边界校验，不含业务规则，不 import ORM/service；
- extra="ignore" 为全局默认；幂等写/导入类端点单独 forbid；
- 必填字符串用 Field(min_length=1) 复刻 request_validation 的
  "缺失/null/空串都视为缺失" 语义。
"""

from app.schemas.common import APIModel, PageQuery  # noqa: F401
