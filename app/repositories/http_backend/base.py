"""HTTP 后端仓储的公共基类与协议工具。

从 dev_vue_http 分支平移的 ``SdkCrudRepository`` 体系：把 DY.Stock.Api 的
标准 CRUD 端点（Delete / GetDataByPageList / GetInfoById / ModifyOrAdd）
转换成本项目仓储层语义的普通字典。与本地 ORM 仓储（app/repositories/*.py）
保持同名同签名，由 app/repositories/__init__.py 按 ``DATA_ACCESS_MODE``
绑定其中一个。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.repositories.sdk_client import SdkProtocolError, StockSdkAdapter


class RemoteRecord(dict):
    """兼容旧服务属性访问的通用远程记录 DTO。"""

    def __getattr__(self, name: str) -> Any:
        """将旧代码的 ``record.field`` 访问映射为字典取值。"""
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        """允许旧代码继续通过属性形式回写远程记录字段。"""
        self[name] = value

    def to_dict(self) -> dict[str, Any]:
        """保持旧服务和路由依赖的序列化接口。"""
        return dict(self)


class HttpRepositoryBase:
    """把 SDK 的标准 CRUD 接口转换成服务层使用的普通字典。"""

    group_name = ""

    def __init__(self, client: StockSdkAdapter | None = None) -> None:
        """注入统一 SDK 适配器，便于测试替换远程客户端。"""
        self.client = client or StockSdkAdapter()

    # ---- 实体流兼容出口（HTTP 后端无 ORM 会话，均为兼容性空实现） ----

    def transaction(self):
        """多步原子流程兼容出口：HTTP 每次调用独立提交，无法跨调用原子。

        TODO(db-to-http): 远端未提供事务端点，此处退化为顺序独立提交；
        中途失败会留下部分写入。涉及强一致的流程（占用配对、执行链记账）
        在迁移文档《无法接入清单》中逐条登记。
        """
        import contextlib

        @contextlib.contextmanager
        def _noop():
            yield

        return _noop()

    def flush(self):
        """实体流兼容出口：HTTP 无会话缓冲，空操作。"""

    def commit(self):
        """实体流兼容出口：HTTP 写方法已在调用内提交，空操作。"""

    def rollback(self):
        """实体流兼容出口：HTTP 无服务端事务可回滚，空操作。"""

    def commit_with_retry(self, operation=None):
        """带重试的提交兼容出口：重试由传输层超时/重试语义承担。

        operation 提供时立即重放一次（HTTP 调用本身幂等性由远端
        ModifyOrAdd 语义保证），不提供时为空操作。
        """
        if operation is not None:
            operation(None)

    # ---- 读写主通路 ----

    def page(
        self,
        payload: Mapping[str, Any],
        *,
        page_index: int = 1,
        page_size: int = 200,
        order_field: str | None = None,
        order_type: str | None = None,
        group: str | None = None,
    ) -> dict[str, Any]:
        """读取一页数据；排序字段仅在调用方明确指定时透传。

        group 供双表仓储（如 task_results + returns）覆盖目标控制器。
        total 派生顺序：分页对象内字段 > 信封 ``ret_count`` > 当页条数。
        """
        body: dict[str, Any] = dict(payload or {})
        body["page_index"] = max(1, int(page_index))
        body["page_size"] = max(1, int(page_size))
        if order_field:
            body["order_field"] = order_field
        if order_type:
            body["order_type"] = order_type
        raw, ret_count = self.client.call_with_count(
            group or self.group_name, "get_data_by_page_list", body
        )
        return self._normalize_page(raw, ret_count)

    def list_all(self, payload: Mapping[str, Any] | None = None, *, page_size: int = 200) -> list[dict[str, Any]]:
        """按过滤条件读取全部分页数据。"""
        return list(self.iter_pages(payload or {}, page_size=page_size))

    def iter_pages(
        self,
        payload: Mapping[str, Any],
        *,
        order_field: str | None = None,
        order_type: str | None = None,
        page_size: int = 200,
        group: str | None = None,
    ):
        """遍历过滤条件命中的全部记录（生成器），按 total 判断翻页结束。"""
        page_index = 1
        while True:
            page = self.page(
                payload,
                page_index=page_index,
                page_size=page_size,
                order_field=order_field,
                order_type=order_type,
                group=group,
            )
            items = page["items"]
            if not items:
                return
            yield from items
            if len(items) < page_size or page_index * page_size >= page["total"]:
                return
            page_index += 1

    def get(self, record_id: int | str) -> dict[str, Any] | None:
        """按主键读取一条记录，未找到时返回 ``None``。"""
        raw = self.client.call(
            self.group_name, "get_info_by_id", {"id": self.normalize_id(record_id)}
        )
        if raw is None:
            return None
        return self.normalize_record(self._as_mapping(raw, "详情"))

    def save(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """调用远端新增/更新接口并标准化返回记录。

        部分远端 ``ModifyOrAdd`` 接口只返回成功信封
        （``ret_code`` / ``ret_msg`` / ``ret_count``），不携带 ``ret_obj``。
        此时 SDK 适配器已经验证写入成功，返回本次提交的数据以兼容调用方。
        """
        api_payload = self.to_api_payload(payload)
        raw = self.client.call(self.group_name, "modify_or_add", api_payload)
        if raw is None:
            return self.normalize_record(api_payload)
        return self.normalize_record(self._as_mapping(raw, "保存结果"))

    def delete(self, record_id: int | str) -> None:
        """按主键删除远端记录。"""
        self.client.call(self.group_name, "delete", {"id": self.normalize_id(record_id)})

    @staticmethod
    def normalize_id(record_id: Any) -> int | str:
        """标准 CRUD 默认使用数值主键；字符串主键资源由子类覆盖。"""
        return int(record_id)

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """为子类预留请求字段转换入口。"""
        return dict(payload)

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """为子类预留响应字段标准化入口。"""
        return dict(record)

    def _normalize_page(self, raw: Any, ret_count: int | None = None) -> dict[str, Any]:
        """兼容 SDK 的列表或分页对象响应，统一输出 ``items`` 与 ``total``。"""
        if isinstance(raw, list):
            items = [
                self.normalize_record(self._as_mapping(item, "列表项")) for item in raw
            ]
            total = ret_count if ret_count is not None else len(items)
            return {"items": items, "total": int(total)}
        data = self._as_mapping(raw, "分页结果")
        inner = next(
            (data[key] for key in ("items", "list", "records", "data") if isinstance(data.get(key), list)),
            None,
        )
        if inner is None:
            raise SdkProtocolError("远程分页响应缺少列表字段")
        items = [self.normalize_record(self._as_mapping(item, "列表项")) for item in inner]
        total = next(
            (data[key] for key in ("total", "total_count", "count") if data.get(key) is not None),
            ret_count if ret_count is not None else len(items),
        )
        return {"items": items, "total": int(total)}

    @staticmethod
    def _as_mapping(value: Any, context: str) -> Mapping[str, Any]:
        """校验 SDK 返回值为对象映射，否则抛出协议异常。"""
        if not isinstance(value, Mapping):
            raise SdkProtocolError(f"远程{context}不是对象")
        return value


def iso_or_none(value: Any) -> Any:
    """datetime/date → ISO 字符串；其余原样返回（None 透传）。"""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def dump_row(
    payload: Mapping[str, Any],
    datetime_fields: tuple[str, ...] = (),
    json_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """把本地字段值转换为远端可序列化载荷：datetime → ISO，dict/list → JSON 串。"""
    result: dict[str, Any] = {}
    for key, value in dict(payload).items():
        if key in json_fields and isinstance(value, (dict, list)):
            import json as _json

            value = _json.dumps(value, ensure_ascii=False)
        elif key in datetime_fields:
            value = iso_or_none(value)
        result[key] = value
    return result


def normalize_bool_fields(record: Mapping[str, Any], *field_names: str) -> dict[str, Any]:
    """把远端可能以字符串或数字表示的布尔字段转换为 ``bool``。"""
    result = dict(record)
    for field_name in field_names:
        if field_name in result and result[field_name] is not None:
            value = result[field_name]
            result[field_name] = (
                value
                if isinstance(value, bool)
                else str(value).strip().lower() in {"1", "true", "yes", "on"}
            )
    return result


def require_remote_mapping(value: Any, context: str) -> dict[str, Any]:
    """断言远端返回对象并拷贝为字典；否则抛协议异常。"""
    if not isinstance(value, Mapping):
        raise SdkProtocolError(f"远程{context}不是对象")
    return dict(value)
