from flask import Blueprint, request, jsonify
import json
from sqlalchemy.orm import load_only

from app.models import TaskTemplate, Task, TaskResult, db
from app.utils.logger import get_logger
from app.utils.auth import login_required

logger = get_logger(__name__)

template_api_bp = Blueprint('template_api', __name__)

@template_api_bp.route('/templates', methods=['GET'])
@login_required
def get_templates():
    """获取所有任务模板"""
    try:
        task_type = request.args.get('task_type')
        templates = TaskTemplate.query.order_by(TaskTemplate.created_at.desc()).all()

        if task_type:
            filtered = []
            for t in templates:
                try:
                    cfg = json.loads(t.config) if isinstance(t.config, str) else t.config
                except Exception:
                    continue
                if isinstance(cfg, dict) and cfg.get('task_type') == task_type:
                    filtered.append(t)
            templates = filtered

        return jsonify({
            "status": "success",
            "templates": [template.to_dict() for template in templates]
        })
    except Exception as e:
        logger.error(f"获取模板列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/templates', methods=['POST'])
@login_required
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

        template = TaskTemplate(
            name=data['name'],
            description=data.get('description', ''),
            config=config_str
        )

        db.session.add(template)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "模板创建成功",
            "template": template.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建模板失败: {str(e)}")
        return jsonify({"status": "error", "message": f"创建模板失败: {str(e)}"}), 500

@template_api_bp.route('/templates/<int:template_id>', methods=['GET'])
@login_required
def get_template(template_id):
    """获取模板详情"""
    try:
        template = TaskTemplate.query.get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404

        return jsonify(template.to_dict())
    except Exception as e:
        logger.error(f"获取模板详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/templates/<int:template_id>', methods=['PUT'])
@login_required
def update_template(template_id):
    """更新任务模板"""
    try:
        template = TaskTemplate.query.get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400

        template.name = data['name']
        template.description = data.get('description', template.description)
        template.config = json.dumps(data['config']) if isinstance(data['config'], (dict, list)) else data['config']

        db.session.commit()

        return jsonify({"status": "success", "template": template.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新模板失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_template(template_id):
    """删除任务模板"""
    try:
        template = TaskTemplate.query.get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404

        db.session.delete(template)
        db.session.commit()

        return jsonify({"status": "success", "message": "模板已删除"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除模板失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/results', methods=['GET'])
@login_required
def get_results():
    """获取任务结果列表"""
    try:
        page = max(request.args.get('page', 1, type=int) or 1, 1)
        per_page = min(request.args.get('per_page', 20, type=int) or 20, 100)
        task_id = request.args.get('task_id', None)

        query = TaskResult.query.join(Task, Task.id == TaskResult.task_id).options(
            load_only(
                TaskResult.id,
                TaskResult.task_id,
                TaskResult.step_index,
                TaskResult.success,
                TaskResult.timestamp,
            )
        )

        if task_id:
            task_obj = (
                Task.query
                .options(load_only(Task.id, Task.task_type))
                .filter(Task.id == task_id)
                .first()
            )
            if not task_obj:
                return jsonify({
                    "results": [],
                    "total": 0,
                    "pages": 0,
                    "current_page": page
                })

            query = query.filter(TaskResult.task_id == task_id)
        else:
            distinct_types = [item[0] for item in db.session.query(Task.task_type).distinct().all()]
            if not distinct_types:
                return jsonify({
                    "results": [],
                    "total": 0,
                    "pages": 0,
                    "current_page": page
                })
            query = query.filter(Task.task_type.in_(distinct_types))

        pagination = query.order_by(TaskResult.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        results = [
            {
                "id": result.id,
                "task_id": result.task_id,
                "step_index": result.step_index,
                "success": result.success,
                "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            }
            for result in pagination.items
        ]

        return jsonify({
            "results": results,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page
        })
    except Exception as e:
        logger.error(f"获取结果列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/results/<int:result_id>', methods=['GET'])
@login_required
def get_result(result_id):
    """获取任务结果详情"""
    try:
        record = (
            db.session.query(TaskResult, Task.task_type)
            .join(Task, Task.id == TaskResult.task_id)
            .filter(TaskResult.id == result_id)
            .first()
        )
        if not record:
            return jsonify({"status": "error", "message": "结果不存在"}), 404

        result, task_type = record

        return jsonify(result.to_dict())
    except Exception as e:
        logger.error(f"获取结果详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@template_api_bp.route('/results/<int:result_id>', methods=['DELETE'])
@login_required
def delete_result(result_id):
    """删除任务结果"""
    try:
        record = (
            db.session.query(TaskResult, Task.task_type)
            .join(Task, Task.id == TaskResult.task_id)
            .filter(TaskResult.id == result_id)
            .first()
        )
        if not record:
            return jsonify({"status": "error", "message": "结果不存在"}), 404

        result, task_type = record

        db.session.delete(result)
        db.session.commit()

        return jsonify({"status": "success", "message": "结果已删除"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除结果失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
