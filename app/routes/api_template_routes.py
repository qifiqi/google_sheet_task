import json

from flask import jsonify, request

from app.models import TaskTemplate, db
from app.services.config_schema import normalize_task_config, validate_task_config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def register_template_routes(api_bp):
    """注册模板相关路由。"""

    @api_bp.route("/templates", methods=["GET"])
    def get_templates():
        """获取所有任务模板。"""
        try:
            task_type = request.args.get("task_type")
            templates = TaskTemplate.query.order_by(TaskTemplate.created_at.desc()).all()

            if task_type:
                filtered = []
                for template in templates:
                    try:
                        cfg = json.loads(template.config) if isinstance(template.config, str) else template.config
                        cfg = normalize_task_config(
                            cfg,
                            task_type=cfg.get("task_type") if isinstance(cfg, dict) else None,
                        )
                    except Exception:
                        continue
                    if isinstance(cfg, dict) and cfg.get("task_type") == task_type:
                        filtered.append(template)
                templates = filtered

            return jsonify({"status": "success", "templates": [template.to_dict() for template in templates]})
        except Exception as exc:
            logger.error(f"获取模板列表失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/templates", methods=["POST"])
    def create_template():
        """创建模板。"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "请求数据为空"}), 400
            if "name" not in data:
                return jsonify({"status": "error", "message": "模板名称不能为空"}), 400
            if "config" not in data:
                return jsonify({"status": "error", "message": "配置信息不能为空"}), 400

            try:
                config_json = json.loads(data["config"]) if isinstance(data["config"], str) else data["config"]
                task_type = config_json.get("task_type") if isinstance(config_json, dict) else None
                normalized_config = normalize_task_config(config_json, task_type=task_type)
                validate_task_config(normalized_config, task_type=task_type)
                config_str = json.dumps(normalized_config)
            except json.JSONDecodeError:
                return jsonify({"status": "error", "message": "配置信息不是有效的 JSON 格式"}), 400
            except ValueError as exc:
                return jsonify({"status": "error", "message": str(exc)}), 400

            template = TaskTemplate(
                name=data["name"],
                description=data.get("description", ""),
                config=config_str,
            )
            db.session.add(template)
            db.session.commit()
            return jsonify({"status": "success", "message": "模板创建成功", "template": template.to_dict()})
        except Exception as exc:
            db.session.rollback()
            logger.error(f"创建模板失败: {str(exc)}")
            return jsonify({"status": "error", "message": f"创建模板失败: {str(exc)}"}), 500

    @api_bp.route("/templates/<int:template_id>", methods=["GET"])
    def get_template(template_id):
        """获取模板详情。"""
        try:
            template = TaskTemplate.query.get(template_id)
            if not template:
                return jsonify({"status": "error", "message": "模板不存在"}), 404

            template_data = template.to_dict()
            config = template_data.get("config")
            if isinstance(config, dict):
                template_data["config"] = normalize_task_config(config, task_type=config.get("task_type"))
            return jsonify(template_data)
        except Exception as exc:
            logger.error(f"获取模板详情失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/templates/<int:template_id>", methods=["PUT"])
    def update_template(template_id):
        """更新模板。"""
        try:
            template = TaskTemplate.query.get(template_id)
            if not template:
                return jsonify({"status": "error", "message": "模板不存在"}), 404

            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "请求数据为空"}), 400

            template.name = data["name"]
            template.description = data.get("description", template.description)
            raw_config = data["config"]
            if isinstance(raw_config, str):
                raw_config = json.loads(raw_config)
            task_type = raw_config.get("task_type") if isinstance(raw_config, dict) else None
            normalized_config = normalize_task_config(raw_config, task_type=task_type)
            validate_task_config(normalized_config, task_type=task_type)
            template.config = json.dumps(normalized_config)

            db.session.commit()
            return jsonify({"status": "success", "template": template.to_dict()})
        except Exception as exc:
            db.session.rollback()
            logger.error(f"更新模板失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/templates/<int:template_id>", methods=["DELETE"])
    def delete_template(template_id):
        """删除模板。"""
        try:
            template = TaskTemplate.query.get(template_id)
            if not template:
                return jsonify({"status": "error", "message": "模板不存在"}), 404

            db.session.delete(template)
            db.session.commit()
            return jsonify({"status": "success", "message": "模板已删除"})
        except Exception as exc:
            db.session.rollback()
            logger.error(f"删除模板失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500
