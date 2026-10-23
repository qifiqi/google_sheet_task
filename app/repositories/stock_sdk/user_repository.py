"""内置股票服务（stock_sdk）用户信息仓储。

外部 Token（非本站签发）校验的唯一接缝：调 stock_sdk 的
``SysUser/GetUserInfo``（Token 走请求头），通过返回身份，未通过返回 None。
网络/HTTP 异常不在此吞掉，由调用方决定拒绝策略。
"""

from __future__ import annotations

from typing import Any

from stock_sdk import StockClient


def get_user_info(token: str, *, base_url: str, timeout: float = 5.0) -> dict[str, Any] | None:
    """校验外部 Token，返回 {'username', 'userid'}；业务未通过返回 None。"""
    client = StockClient(token=token, base_url=base_url, timeout=timeout)
    try:
        response = client.sys_user.get_user_info()
    finally:
        client.close()

    if not response.is_success:
        return None
    obj = response.ret_obj if isinstance(response.ret_obj, dict) else {}
    username = str(obj.get('username') or '').strip()
    if not username:
        return None
    return {'username': username, 'userid': obj.get('userid')}
