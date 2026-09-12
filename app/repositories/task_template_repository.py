"""TaskTemplate 仓储（契约见 docs/design/data-layer-refactor/02 §2.4）。"""
from app.extensions import db
from app.exceptions import NotFoundError
from app.models import TaskTemplate
from app.repositories.base import BaseRepository


class TaskTemplateRepository(BaseRepository):
    model = TaskTemplate

    # ---- 读 ----

    def list_all(self, task_type=None):
        """保持现有 Python 端过滤语义：解析 config JSON 后按 config.task_type 过滤，
        解析失败的模板跳过。"""
        templates = TaskTemplate.query.order_by(TaskTemplate.created_at.desc()).all()
        results = []
        for template in templates:
            data = template.to_dict()
            if task_type:
                config = data.get("config")
                if not isinstance(config, dict) or config.get("task_type") != task_type:
                    continue
            results.append(data)
        return results

    def get(self, template_id):
        template = db.session.get(TaskTemplate, template_id)
        return template.to_dict() if template else None

    def get_required(self, template_id):
        data = self.get(template_id)
        if data is None:
            raise NotFoundError(f"模板不存在: {template_id}")
        return data

    # ---- 写 ----

    def create(self, name, description, config_str):
        template = TaskTemplate(
            name=name,
            description=description,
            config=config_str,
        )
        db.session.add(template)
        self._commit()
        return template.to_dict()

    def update(self, template_id, fields):
        template = db.session.get(TaskTemplate, template_id)
        if template is None:
            return None
        for key, value in fields.items():
            setattr(template, key, value)
        self._commit()
        return template.to_dict()

    def delete(self, template_id, commit=True):
        template = db.session.get(TaskTemplate, template_id)
        if template is None:
            return False
        db.session.delete(template)
        if commit:
            self._commit()
        return True
