"""系统日志 API（自 config_api.py 归位，URL 不变）。

日志文件解析属表现层读取（非 ORM），留在路由层。
"""

from flask import Blueprint, request

from app.utils.api_response import success
from app.utils.auth import login_required

logs_api_bp = Blueprint('logs_api', __name__)


@logs_api_bp.route('/logs', methods=['GET'])
@login_required
def get_logs():
    """获取系统日志"""
    import os
    import re
    from app.config import Config

    limit = request.args.get('limit', 100, type=int)
    level_filter = request.args.get('level', '')
    search = request.args.get('search', '')
    date_filter = request.args.get('date', '')
    task_id_filter = request.args.get('task_id', '')

    log_file = Config.LOG_FILE
    parsed_logs = []

    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent_lines = lines[-limit*3:] if len(lines) > limit*3 else lines

            log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'

            for line in recent_lines:
                line = line.strip()
                if not line:
                    continue

                match = re.match(log_pattern, line)
                if match:
                    timestamp_str, source, level, message = match.groups()

                    try:
                        from datetime import datetime
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        iso_timestamp = timestamp.isoformat()
                    except Exception:
                        iso_timestamp = timestamp_str

                    log_entry = {
                        'timestamp': iso_timestamp,
                        'level': level.lower(),
                        'message': message.strip(),
                        'source': source.strip()
                    }

                    if level_filter and log_entry['level'] != level_filter.lower():
                        continue
                    if search and search.lower() not in log_entry['message'].lower():
                        continue
                    if date_filter and not iso_timestamp.startswith(date_filter):
                        continue
                    if task_id_filter:
                        task_pattern = f"[Task-{task_id_filter[:8]}]"
                        if task_pattern not in log_entry['message'] and task_id_filter not in log_entry['message']:
                            continue

                    parsed_logs.append(log_entry)
                else:
                    parsed_logs.append({
                        'timestamp': '',
                        'level': 'info',
                        'message': line,
                        'source': 'unknown'
                    })

            parsed_logs.reverse()
            parsed_logs = parsed_logs[:limit]

    return success(data={"logs": parsed_logs})


@logs_api_bp.route('/logs/latest', methods=['GET'])
@login_required
def get_latest_logs():
    """获取最新的日志"""
    import os
    import re
    from app.config import Config

    since = request.args.get('since', '')
    limit = request.args.get('limit', 50, type=int)

    log_file = Config.LOG_FILE
    latest_logs = []

    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            recent_lines = lines[-limit*2:] if len(lines) > limit*2 else lines

            log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'

            for line in recent_lines:
                line = line.strip()
                if not line:
                    continue

                match = re.match(log_pattern, line)
                if match:
                    timestamp_str, source, level, message = match.groups()

                    try:
                        from datetime import datetime
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                        iso_timestamp = timestamp.isoformat()
                    except Exception:
                        iso_timestamp = timestamp_str

                    if since and iso_timestamp <= since:
                        continue

                    log_entry = {
                        'timestamp': iso_timestamp,
                        'level': level.lower(),
                        'message': message.strip(),
                        'source': source.strip()
                    }

                    latest_logs.append(log_entry)

            latest_logs.sort(key=lambda x: x['timestamp'])
            latest_logs = latest_logs[-limit:]

    return success(data={"logs": latest_logs})
