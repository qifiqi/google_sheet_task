import os
import re
from datetime import datetime

from flask import jsonify, request

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_log_line(line: str):
    """解析单行系统日志。"""
    log_pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)"
    match = re.match(log_pattern, line)
    if not match:
        return None

    timestamp_str, source, level, message = match.groups()
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
        iso_timestamp = timestamp.isoformat()
    except Exception:
        iso_timestamp = timestamp_str

    return {
        "timestamp": iso_timestamp,
        "level": level.lower(),
        "message": message.strip(),
        "source": source.strip(),
    }


def register_log_routes(api_bp):
    """注册日志相关路由。"""

    @api_bp.route("/tasks/<task_id>/system-logs", methods=["GET"])
    def get_task_system_logs(task_id):
        """获取任务相关系统日志。"""
        try:
            limit = request.args.get("limit", 200, type=int)
            level_filter = request.args.get("level", "")
            task_logs = []

            if os.path.exists(Config.LOG_FILE):
                with open(Config.LOG_FILE, "r", encoding="utf-8") as file:
                    lines = file.readlines()

                task_patterns = [f"[Task-{task_id[:8]}]", f"任务 {task_id}", task_id]
                for line in lines:
                    line = line.strip()
                    if not line or not any(pattern in line for pattern in task_patterns):
                        continue

                    log_entry = _parse_log_line(line)
                    if not log_entry:
                        continue
                    log_entry["task_id"] = task_id
                    if level_filter and log_entry["level"] != level_filter.lower():
                        continue
                    task_logs.append(log_entry)

            task_logs.sort(key=lambda item: item["timestamp"])
            task_logs = task_logs[-limit:]
            return jsonify(
                {
                    "status": "success",
                    "logs": task_logs,
                    "task_id": task_id,
                    "total_found": len(task_logs),
                }
            )
        except Exception as exc:
            logger.error(f"获取任务系统日志失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/logs", methods=["GET"])
    def get_logs():
        """获取系统日志。"""
        try:
            limit = request.args.get("limit", 100, type=int)
            level_filter = request.args.get("level", "")
            search = request.args.get("search", "")
            date_filter = request.args.get("date", "")
            task_id_filter = request.args.get("task_id", "")
            parsed_logs = []

            if os.path.exists(Config.LOG_FILE):
                with open(Config.LOG_FILE, "r", encoding="utf-8") as file:
                    lines = file.readlines()
                recent_lines = lines[-limit * 3 :] if len(lines) > limit * 3 else lines

                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue

                    log_entry = _parse_log_line(line)
                    if not log_entry:
                        parsed_logs.append(
                            {"timestamp": "", "level": "info", "message": line, "source": "unknown"}
                        )
                        continue

                    if level_filter and log_entry["level"] != level_filter.lower():
                        continue
                    if search and search.lower() not in log_entry["message"].lower():
                        continue
                    if date_filter and not log_entry["timestamp"].startswith(date_filter):
                        continue
                    if task_id_filter:
                        task_pattern = f"[Task-{task_id_filter[:8]}]"
                        if task_pattern not in log_entry["message"] and task_id_filter not in log_entry["message"]:
                            continue
                    parsed_logs.append(log_entry)

            parsed_logs.reverse()
            parsed_logs = parsed_logs[:limit]
            return jsonify({"status": "success", "logs": parsed_logs})
        except Exception as exc:
            logger.error(f"获取日志失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500

    @api_bp.route("/logs/latest", methods=["GET"])
    def get_latest_logs():
        """获取最新日志。"""
        try:
            since = request.args.get("since", "")
            limit = request.args.get("limit", 50, type=int)
            latest_logs = []

            if os.path.exists(Config.LOG_FILE):
                with open(Config.LOG_FILE, "r", encoding="utf-8") as file:
                    lines = file.readlines()
                recent_lines = lines[-limit * 2 :] if len(lines) > limit * 2 else lines

                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue
                    log_entry = _parse_log_line(line)
                    if not log_entry:
                        continue
                    if since and log_entry["timestamp"] <= since:
                        continue
                    latest_logs.append(log_entry)

            latest_logs.sort(key=lambda item: item["timestamp"])
            latest_logs = latest_logs[-limit:]
            return jsonify({"status": "success", "logs": latest_logs})
        except Exception as exc:
            logger.error(f"获取最新日志失败: {str(exc)}")
            return jsonify({"status": "error", "message": str(exc)}), 500
