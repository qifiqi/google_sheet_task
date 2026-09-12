"""任务模板服务（数据层：task_template_repository）。

模板 CRUD 编排与 config JSON 规范化收敛于此；路由层只做 HTTP 解析与统一信封。
"""

from __future__ import annotations

import json

from app.exceptions import BadRequestError, NotFoundError
from app.repositories import task_template_repository


class TaskTemplateService:
    """任务模板业务服务。"""

    @staticmethod
    def _serialize_config_str(config) -> str:
        """前端 config 可传 JSON 字符串或对象，统一落库为规范化 JSON 字符串。"""
        if isinstance(config, str):
            try:
                config_json = json.loads(config)
            except json.JSONDecodeError:
                raise BadRequestError("配置信息不是有效的JSON格式")
            return json.dumps(config_json)
        return json.dumps(config)

    def list_templates(self, task_type: str | None = None):
        return task_template_repository.list_all(task_type=task_type)

    def create_template(self, name: str, description: str, config) -> dict:
        return task_template_repository.create(
            name=name,
            description=description,
            config_str=self._serialize_config_str(config),
        )

    def get_template(self, template_id: int) -> dict:
        """模板详情；不存在抛 NotFoundError（仓储契约）。"""
        return task_template_repository.get_required(template_id)

    def update_template(self, template_id: int, *, name, description, config) -> dict:
        template = task_template_repository.get(template_id)
        if template is None:
            raise NotFoundError("模板不存在")
        return task_template_repository.update(template_id, {
            "name": name,
            "description": description if description is not None else template["description"],
            "config": self._serialize_config_str(config),
        })

    def delete_template(self, template_id: int) -> bool:
        """删除模板；不存在抛 NotFoundError。"""
        deleted = task_template_repository.delete(template_id)
        if not deleted:
            raise NotFoundError("模板不存在")
        return deleted


task_template_service = TaskTemplateService()
