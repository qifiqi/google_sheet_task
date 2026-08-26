"""生成 SDK 标准 CRUD 资源的通用适配器。"""

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


class SdkCrudRepository:
    """把 SDK 的标准 CRUD 接口转换成服务层使用的普通字典。"""

    group_name = ""

    def __init__(self, client: StockSdkAdapter | None = None) -> None:
        """注入统一 SDK 适配器，便于测试替换远程客户端。"""
        self.client = client or StockSdkAdapter()

    def list_page(
        self,
        *,
        page_index: int = 1,
        page_size: int = 200,
        order_field: str | None = None,
        order_type: str | None = None,
    ) -> dict[str, Any]:
        """读取一页数据；排序字段仅在调用方明确指定时透传。"""
        payload: dict[str, Any] = {
            "page_index": max(1, int(page_index)),
            "page_size": max(1, int(page_size)),
        }
        if order_field:
            payload["order_field"] = order_field
        if order_type:
            payload["order_type"] = order_type
        raw = self.client.call(self.group_name, "get_data_by_page_list", payload)
        return self._normalize_page(raw)

    def list_all(self, *, page_size: int = 200) -> list[dict[str, Any]]:
        """读取全部分页数据，不在客户端模拟业务筛选。"""
        page_index = 1
        records: list[dict[str, Any]] = []
        while True:
            page = self.list_page(page_index=page_index, page_size=page_size)
            records.extend(page["items"])
            if not page["items"] or len(records) >= page["total"]:
                return records
            page_index += 1

    def get(self, record_id: int | str) -> dict[str, Any] | None:
        """按主键读取一条记录，未找到时返回 ``None``。"""
        raw = self.client.call(self.group_name, "get_info_by_id", {"id": self.normalize_id(record_id)})
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
        raw = self.client.call(
            self.group_name,
            "modify_or_add",
            api_payload,
        )
        if raw is None:
            return self.normalize_record(api_payload)
        return self.normalize_record(self._as_mapping(raw, "保存结果"))

    def delete(self, record_id: int) -> None:
        """按主键删除远端记录。"""
        self.client.call(self.group_name, "delete", {"id": self.normalize_id(record_id)})

    @staticmethod
    def normalize_id(record_id: Any) -> int:
        """标准 CRUD 默认使用数值主键；字符串主键资源由子类覆盖。"""
        return int(record_id)

    def to_api_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """为子类预留请求字段转换入口。"""
        return dict(payload)

    def normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """为子类预留响应字段标准化入口。"""
        return dict(record)

    def _normalize_page(self, raw: Any) -> dict[str, Any]:
        """兼容 SDK 的列表或分页对象响应，统一输出 ``items`` 与 ``total``。"""
        if isinstance(raw, list):
            return {"items": [self.normalize_record(self._as_mapping(item, "列表项")) for item in raw], "total": len(raw)}
        data = self._as_mapping(raw, "分页结果")
        items = next(
            (data[key] for key in ("items", "list", "records", "data") if isinstance(data.get(key), list)),
            None,
        )
        if items is None:
            raise SdkProtocolError("远程分页响应缺少列表字段")
        total = next((data[key] for key in ("total", "total_count", "count") if data.get(key) is not None), len(items))
        return {
            "items": [self.normalize_record(self._as_mapping(item, "列表项")) for item in items],
            "total": int(total),
        }

    @staticmethod
    def _as_mapping(value: Any, context: str) -> Mapping[str, Any]:
        """校验 SDK 返回值为对象映射，否则抛出协议异常。"""
        if not isinstance(value, Mapping):
            raise SdkProtocolError(f"远程{context}不是对象")
        return value


def normalize_bool_fields(record: Mapping[str, Any], *field_names: str) -> dict[str, Any]:
    """把远端可能以字符串或数字表示的布尔字段转换为 ``bool``。"""
    result = dict(record)
    for field_name in field_names:
        if field_name in result and result[field_name] is not None:
            value = result[field_name]
            result[field_name] = value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "on"}
    return result
