from flask import Blueprint, request, jsonify, g
import json

from app.repositories.task_repository import TaskRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.repositories.template_repository import TaskTemplateRepository
from app.utils.logger import get_logger
from app.utils.auth import login_required, permission_required
from app.utils.task_authorization import authorize_task_type_action

logger = get_logger(__name__)

template_api_bp = Blueprint('template_api', __name__)

TASK_ACTION_LABELS = {
    "view": "查看",
    "delete": "删除",
}


def _template_repository():
    """创建任务模板远程 CRUD 仓储。"""
    return TaskTemplateRepository()


def _result_repository():
    """创建任务结果远程 CRUD 仓储。"""
    return TaskResultRepository()


def _task_repository():
    """创建任务远程 CRUD 仓储。"""
    return TaskRepository()


def _result_permission_denied(
    action: str,
    task_type: str | None,
    decision: dict,
    result_id: int | None = None,
    task_id: str | None = None,
):
    """构造任务结果权限不足时的统一接口响应。"""
    action_label = TASK_ACTION_LABELS.get(action, action)
    normalized_type = decision.get("task_type") or str(task_type or "unknown")
    missing_permissions = decision.get("missing_permissions") or []
    missing_text = "、".join(missing_permissions) if missing_permissions else "未知"
    message = f"权限不足，无法{action_label}{normalized_type}任务结果；当前缺少: {missing_text}"

    return jsonify({
        "status": "error",
        "message": message,
        "action": action,
        "task_type": normalized_type,
        "task_id": task_id,
        "result_id": result_id,
        "required_permissions": decision.get("required_permissions") or [],
        "missing_permissions": missing_permissions,
    }), 403

@template_api_bp.route('/templates', methods=['GET'])
@login_required
@permission_required('template:view')
def get_templates():
    """获取所有任务模板"""
    try:
        task_type = request.args.get('task_type')
        # 仅列表读取迁移到 SDK；按 task_type 的页面筛选沿用现有接口语义。
        templates = _template_repository().list_page(
            page_size=1000,
        )["items"]

        if task_type:
            filtered = []
            for t in templates:
                try:
                    cfg = t.get("config")
                except Exception:
                    continue
                if isinstance(cfg, dict) and cfg.get('task_type') == task_type:
                    filtered.append(t)
            templates = filtered

        return jsonify({
            "status": "success",
            "templates": templates
        })
    except Exception as e:
        logger.error(f"获取模板列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/templates', methods=['POST'])
@login_required
@permission_required('template:manage')
def create_template():
    """创建新任务模板"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400

        if 'name' not in data:
            return jsonify({"status": "error", "message": "模板名称不能为空"}), 400

        if 'config' not in data:
            return jsonify({"status": "error", "message": "配置信息不能为空"}), 400

        try:
            if isinstance(data['config'], str):
                config_json = json.loads(data['config'])
                config_str = json.dumps(config_json)
            else:
                config_str = json.dumps(data['config'])
        except json.JSONDecodeError:
            return jsonify({"status": "error", "message": "配置信息不是有效的JSON格式"}), 400

        # Repository 负责将 config 字典/JSON 文本转换成 SDK 所需格式。
        template = _template_repository().save({
            "name": data['name'],
            "description": data.get('description', ''),
            "config": config_str,
        })

        return jsonify({
            "status": "success",
            "message": "模板创建成功",
            "template": template
        })
    except Exception as e:
        logger.error(f"创建模板失败: {str(e)}")
        return jsonify({"status": "error", "message": f"创建模板失败: {str(e)}"}), 500

@template_api_bp.route('/templates/<int:template_id>', methods=['GET'])
@login_required
@permission_required('template:view')
def get_template(template_id):
    """获取模板详情"""
    try:
        template = _template_repository().get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404

        return jsonify(template)
    except Exception as e:
        logger.error(f"获取模板详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/templates/<int:template_id>', methods=['PUT'])
@login_required
@permission_required('template:manage')
def update_template(template_id):
    """更新任务模板"""
    try:
        template = _template_repository().get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400

        # 更新时显式携带主键，调用远端 modify_or_add 的更新分支。
        template = _template_repository().save({
            "id": template_id,
            "name": data['name'],
            "description": data.get('description', template.get("description", "")),
            "config": data['config'],
        })

        return jsonify({"status": "success", "template": template})
    except Exception as e:
        logger.error(f"更新模板失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/templates/<int:template_id>', methods=['DELETE'])
@login_required
@permission_required('template:manage')
def delete_template(template_id):
    """删除任务模板"""
    try:
        template = _template_repository().get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404

        _template_repository().delete(template_id)

        return jsonify({"status": "success", "message": "模板已删除"})
    except Exception as e:
        logger.error(f"删除模板失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/results', methods=['GET'])
@login_required
@permission_required('task:view')
def get_results():
    """获取任务结果列表"""
    try:
        page = max(request.args.get('page', 1, type=int) or 1, 1)
        per_page = min(request.args.get('per_page', 20, type=int) or 20, 100)
        task_id = request.args.get('task_id', None)
        current_user = getattr(g, "current_user", None)

        if task_id:
            task_obj = _task_repository().get(task_id)
            if not task_obj:
                return jsonify({
                    "results": [],
                    "total": 0,
                    "pages": 0,
                    "current_page": page,
                })

            decision = authorize_task_type_action(
                current_user,
                "view",
                task_obj.task_type,
            )
            if not decision["allowed"]:
                return _result_permission_denied(
                    "view",
                    task_obj.task_type,
                    decision,
                    task_id=task_id,
                )

            remote_page = _result_repository().list_results(
                page_index=page,
                page_size=per_page,
                task_ids=[task_id],
                order_field="timestamp",
                order_type="desc",
            )
            results = [
                {
                    "id": result.id,
                    "task_id": result.task_id,
                    "step_index": result.step_index,
                    "success": result.success,
                    "timestamp": (
                        result.timestamp.isoformat()
                        if getattr(result, "timestamp", None)
                        and hasattr(result.timestamp, "isoformat")
                        else result.get("timestamp")
                    ),
                }
                for result in remote_page["items"]
            ]
            total = remote_page["total"]
            pages = (total + per_page - 1) // per_page if total else 0
            return jsonify({
                "results": results,
                "total": total,
                "pages": pages,
                "current_page": page,
            })

        remote_page = _result_repository().list_results(
            page_index=page,
            page_size=per_page,
            task_ids=[task_id] if task_id else None,
            order_field="timestamp",
            order_type="desc",
        )
        results = [
            {
                "id": result.id,
                "task_id": result.task_id,
                "step_index": result.step_index,
                "success": result.success,
                "timestamp": (
                    result.timestamp.isoformat()
                    if getattr(result, "timestamp", None)
                    and hasattr(result.timestamp, "isoformat")
                    else result.get("timestamp")
                ),
            }
            for result in remote_page["items"]
        ]
        total = remote_page["total"]
        pages = (total + per_page - 1) // per_page if total else 0

        return jsonify({
            "results": results,
            "total": total,
            "pages": pages,
            "current_page": page,
        })
    except Exception as e:
        logger.error(f"获取结果列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/results/<int:result_id>', methods=['GET'])
@login_required
@permission_required('task:view')
def get_result(result_id):
    """获取任务结果详情"""
    try:
        result = _result_repository().get(result_id)
        if not result:
            return jsonify({"status": "error", "message": "结果不存在"}), 404
        task = _task_repository().get(result.task_id)
        if not task:
            return jsonify({"status": "error", "message": "任务不存在"}), 404

        decision = authorize_task_type_action(
            getattr(g, "current_user", None),
            "view",
            task.task_type,
        )
        if not decision["allowed"]:
            return _result_permission_denied(
                "view",
                task.task_type,
                decision,
                result_id=result_id,
                task_id=result.task_id,
            )

        return jsonify(result.to_dict())
    except Exception as e:
        logger.error(f"获取结果详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/results/<int:result_id>', methods=['DELETE'])
@login_required
@permission_required('task:delete')
def delete_result(result_id):
    """删除任务结果"""
    try:
        result = _result_repository().get(result_id)
        if not result:
            return jsonify({"status": "error", "message": "结果不存在"}), 404
        task = _task_repository().get(result.task_id)
        if not task:
            return jsonify({"status": "error", "message": "任务不存在"}), 404

        decision = authorize_task_type_action(
            getattr(g, "current_user", None),
            "delete",
            task.task_type,
        )
        if not decision["allowed"]:
            return _result_permission_denied(
                "delete",
                task.task_type,
                decision,
                result_id=result_id,
                task_id=result.task_id,
            )

        _result_repository().delete(result_id)
        return jsonify({"status": "success", "message": "结果已删除"})
    except Exception as e:
        logger.error(f"删除结果失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
