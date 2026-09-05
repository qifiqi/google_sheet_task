"""SystemConfig 仓储（契约见 docs/design/data-layer-refactor/02 §2.5）。

方向约束：config_manager → system_config_repository，禁止反向 import。
repository 只管 DB 行级读写：
- get_row 返回的 value 保持入库原样字符串，JSON 解析/bool 还原逻辑留在 config_manager；
- 负缓存刷新留在 config_manager 层；调用方写库后必须走 set_config/update_configs
  或显式刷新缓存。
"""
from app.extensions import db
from app.models import SystemConfig
from app.repositories.base import BaseRepository


class SystemConfigRepository(BaseRepository):
    model = SystemConfig

    # ---- 读 ----

    def get_row(self, key):
        """返回 {key, value, description, ...}；value 保持入库原样字符串。不存在返回 None。"""
        row = SystemConfig.query.filter_by(key=key).first()
        return row.to_dict() if row else None

    def list_rows(self):
        """按 key asc 返回全部配置行（config_api 管理端）。"""
        return [
            row.to_dict()
            for row in SystemConfig.query.order_by(SystemConfig.key.asc()).all()
        ]

    def list_key_descriptions(self):
        """[{key, description}]（config.py 启动期读取）。"""
        rows = (
            SystemConfig.query
            .with_entities(SystemConfig.key, SystemConfig.description)
            .order_by(SystemConfig.key.asc())
            .all()
        )
        return [{"key": key, "description": description} for key, description in rows]

    # ---- 写 ----

    def update(self, key, fields, commit=True):
        """按 key 更新指定列（值可为 None，用于清空）；key 不存在返回 None。"""
        row = SystemConfig.query.filter_by(key=key).first()
        if row is None:
            return None
        for field, value in fields.items():
            setattr(row, field, value)
        if commit:
            self._commit()
        return row.to_dict()

    def upsert(self, key, value, description=None, commit=True):
        """写入或更新一行；不负责缓存刷新（调用方负责走 set_config/update_configs 或刷新缓存）。"""
        row = SystemConfig.query.filter_by(key=key).first()
        if row is None:
            row = SystemConfig(key=key, value=value)
            if description is not None:
                row.description = description
            db.session.add(row)
        else:
            row.value = value
            if description is not None:
                row.description = description
        if commit:
            self._commit()
        return row.to_dict()

    def delete(self, key, commit=True):
        deleted = (
            SystemConfig.query.filter_by(key=key)
            .delete(synchronize_session=False)
        )
        if commit:
            self._commit()
        return deleted > 0
