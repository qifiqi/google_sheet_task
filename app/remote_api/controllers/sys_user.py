"""``/api/SysUser`` —— 系统用户与身份接口。

每个方法对应远程的一个具体端点，docstring 内含等价 curl 调用示例；
请求统一经 ``app/remote_api/client.py`` 的 ``StockApiClient`` 发出
（Token 请求头、统一信封解包、异常翻译、布尔 0/1 编码都在那里完成）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.remote_api.base import ControllerApi


class SysUserApi(ControllerApi):
    """系统用户与身份接口（远程控制器 ``/api/SysUser``）。

    ``get`` / ``get_user_info`` / ``get_user_role_list`` 的用户凭据只能走
    ``Token`` 请求头，方法签名显式接收 ``token``；登录接口使用服务级
    凭据（不绑定用户 Token）。
    """

    def get(self, *, token: str) -> Any:
        """
        读取当前登录用户（请求体恒为空对象，凭据只走 Token 请求头）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/Get' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -H 'Token: <token>' \
              -d '{}'
        """
        return self._make_request('POST', '/api/SysUser/Get', {}, token=token)

    def get_by_id(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        按主键查询用户详情

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/GetById' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/SysUser/GetById', payload)

    def get_data_by_page_list(self, payload: Mapping[str, Any] | None = None) -> tuple[Any, int | None]:
        """
        分页查询用户（支持 username/role_name 等过滤）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/GetDataByPageList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"page_index": 1, "page_size": 20}'

        返回 ``(ret_obj, ret_count)``：ret_count 为匹配总记录数，远端未返回时为 None。
        """
        return self._make_request_with_count('POST', '/api/SysUser/GetDataByPageList', payload)

    def get_list_for_select(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        查询用户下拉选项列表（请求体恒为空对象）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/GetListForSelect' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{}'
        """
        return self._make_request('POST', '/api/SysUser/GetListForSelect', payload)

    def get_user_info(self, *, token: str) -> Any:
        """
        用请求头 Token 校验身份并返回用户信息（请求体恒为空对象）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/GetUserInfo' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -H 'Token: <token>' \
              -d '{}'
        """
        return self._make_request('POST', '/api/SysUser/GetUserInfo', {}, token=token)

    def get_user_role_list(self, *, token: str) -> Any:
        """
        用请求头 Token 读取用户可访问模型/路由表（请求体恒为空对象）

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/GetUserRoleList' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -H 'Token: <token>' \
              -d '{}'
        """
        return self._make_request('POST', '/api/SysUser/GetUserRoleList', {}, token=token)

    def login(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        账号密码登录，颁发用户 Token

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/Login' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"user_name": "...", "user_password": "..."}'
        """
        return self._make_request('POST', '/api/SysUser/Login', payload)

    def pwd_reset(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        管理员重置用户密码

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/PwdReset' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1}'
        """
        return self._make_request('POST', '/api/SysUser/PwdReset', payload)

    def register(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        注册新用户

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/Register' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"user_name": "...", "user_password": "..."}'
        """
        return self._make_request('POST', '/api/SysUser/Register', payload)

    def update_pwd(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        用户修改自身密码

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/UpdatePwd' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"old_password": "...", "new_password": "..."}'
        """
        return self._make_request('POST', '/api/SysUser/UpdatePwd', payload)

    def update_user_role(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        更新用户角色

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/UpdateUserRole' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"userid": 1, "role_id": 1}'
        """
        return self._make_request('POST', '/api/SysUser/UpdateUserRole', payload)

    def user_enable_or_un_enable(self, payload: Mapping[str, Any] | None = None) -> Any:
        """
        启用/停用用户

            curl -X 'POST' \
              'http://stockapi.stplan.cn/api/SysUser/UserEnableOrUnEnable' \
              -H 'accept: application/json' \
              -H 'Content-Type: application/json' \
              -d '{"id": 1, "state": 1}'
        """
        return self._make_request('POST', '/api/SysUser/UserEnableOrUnEnable', payload)
