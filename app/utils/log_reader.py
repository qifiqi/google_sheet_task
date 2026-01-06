import os
import re
from datetime import datetime
from typing import List, Dict, Optional

from app.config import Config


LOG_PATTERN = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)"


def _parse_log_line(line: str) -> Optional[Dict[str, str]]:
    line = line.strip()
    if not line:
        return None
    match = re.match(LOG_PATTERN, line)
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


def read_logs(limit: int = 100,
              level: str = "",
              search: str = "",
              date_prefix: str = "",
              task_id: str = "",
              since: str = "",
              task_only: bool = False) -> List[Dict[str, str]]:
    log_file = Config.LOG_FILE
    if not os.path.exists(log_file):
        return []

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 为控制性能，只从尾部读取一定倍数
    base_multiplier = 3 if not since else 2
    slice_len = limit * base_multiplier
    recent_lines = lines[-slice_len:] if len(lines) > slice_len else lines

    task_patterns: List[str] = []
    if task_id:
        task_patterns = [f"[Task-{task_id[:8]}]", f"任务 {task_id}", task_id]

    results: List[Dict[str, str]] = []

    for raw_line in recent_lines:
        parsed = _parse_log_line(raw_line)
        if not parsed:
            # 无法解析时，保留原始信息
            results.append({
                "timestamp": "",
                "level": "info",
                "message": raw_line.strip(),
                "source": "unknown",
            })
            continue

        if since and parsed["timestamp"] <= since:
            continue

        if level and parsed["level"] != level.lower():
            continue

        if search and search.lower() not in parsed["message"].lower():
            continue

        if date_prefix and not parsed["timestamp"].startswith(date_prefix):
            continue

        if task_only and task_patterns:
            if not any(p in parsed["message"] for p in task_patterns):
                continue

        results.append(parsed)

    # 排序与截断：
    results.sort(key=lambda x: x["timestamp"])
    if since:
        # since 模式通常需要最新在后，这里保持正序
        return results[-limit:]

    # 普通模式：返回最新 limit 条，按时间倒序
    results = results[-limit:]
    results.reverse()
    return results
