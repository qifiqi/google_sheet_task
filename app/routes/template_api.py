"""任务模板 API（数据层：task_template_repository）。

异常处理约定：路由内不写 try/except 兜底，由 app/errors.py 全局处理器统一转信封。
"""
import json

from flask import Blueprint, request

from app.exceptions import BadRequestError, NotFoundError
from app.repositories import task_template_repository
from app.utils.api_response import success
from app.utils.auth import login_required
from app.schemas.template import TemplateCreateSchema, TemplateUpdateSchema
from app.utils.request_parsing import parse_body

template_api_bp = Blueprint('template_api', __name__)


def _serialize_config_str(config) -> str:
    """前端 config 可传 JSON 字符串或对象，统一落库为规范化 JSON 字符串。"""
    if isinstance(config, str):
        try:
            config_json = json.loads(config)
        except json.JSONDecodeError:
            raise BadRequestError("配置信息不是有效的JSON格式")
        return json.dumps(config_json)
    return json.dumps(config)


@template_api_bp.route('/templates', methods=['GET'])
@login_required
def get_templates():
    """获取所有任务模板"""
    task_type = request.args.get('task_type')
    templates = task_template_repository.list_all(task_type=task_type)
    return success(data={"templates": templates})


@template_api_bp.route('/templates', methods=['POST'])
@login_required
def create_template():
    """创建新任务模板"""
    data = parse_body(TemplateCreateSchema)
    template = task_template_repository.create(
        name=data.name,
        description=data.description,
        config_str=_serialize_config_str(data.config),
    )
    return success(data={"template": template}, message="模板创建成功")


@template_api_bp.route('/templates/<int:template_id>', methods=['GET'])
@login_required
def get_template(template_id):
    """获取模板详情"""
    template = task_template_repository.get_required(template_id)
    return success(data=template)


@template_api_bp.route('/templates/<int:template_id>', methods=['PUT'])
@login_required
def update_template(template_id):
    """更新任务模板"""
    template = task_template_repository.get(template_id)
    if template is None:
        raise NotFoundError("模板不存在")

    data = parse_body(TemplateUpdateSchema)
    updated = task_template_repository.update(template_id, {
        "name": data.name,
        "description": data.description if data.description is not None else template['description'],
        "config": _serialize_config_str(data.config),
    })
    return success(data={"template": updated})


@template_api_bp.route('/templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_template(template_id):
    """删除任务模板"""
    deleted = task_template_repository.delete(template_id)
    if not deleted:
        raise NotFoundError("模板不存在")
    return success(message="模板已删除")
