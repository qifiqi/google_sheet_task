"""任务模板 API。

模板 CRUD 编排与 config JSON 规范化在 task_template_service；
路由层只做 HTTP 解析与统一信封，异常交 app/errors.py 全局处理器。
"""
from flask import Blueprint, request

from app.services.task_template_service import task_template_service
from app.utils.api_response import success
from app.utils.auth import login_required
from app.schemas.template import TemplateCreateSchema, TemplateUpdateSchema
from app.utils.request_parsing import parse_body

template_api_bp = Blueprint('template_api', __name__)


@template_api_bp.route('/templates', methods=['GET'])
@login_required
def get_templates():
    """获取所有任务模板"""
    task_type = request.args.get('task_type')
    templates = task_template_service.list_templates(task_type=task_type)
    return success(data={"templates": templates})


@template_api_bp.route('/templates', methods=['POST'])
@login_required
def create_template():
    """创建新任务模板"""
    data = parse_body(TemplateCreateSchema)
    template = task_template_service.create_template(
        name=data.name,
        description=data.description,
        config=data.config,
    )
    return success(data={"template": template}, message="模板创建成功")


@template_api_bp.route('/templates/<int:template_id>', methods=['GET'])
@login_required
def get_template(template_id):
    """获取模板详情"""
    template = task_template_service.get_template(template_id)
    return success(data=template)


@template_api_bp.route('/templates/<int:template_id>', methods=['PUT'])
@login_required
def update_template(template_id):
    """更新任务模板"""
    data = parse_body(TemplateUpdateSchema)
    updated = task_template_service.update_template(
        template_id,
        name=data.name,
        description=data.description,
        config=data.config,
    )
    return success(data={"template": updated})


@template_api_bp.route('/templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_template(template_id):
    """删除任务模板"""
    task_template_service.delete_template(template_id)
    return success(message="模板已删除")
