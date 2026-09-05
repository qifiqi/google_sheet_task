"""日志文件查询服务（表现层读取：解析 Config.LOG_FILE 文本，非 ORM）。

2026-09 审计 B3：logs_api（/logs、/logs/latest）与 task_api（/tasks/<id>/system-logs）
的三份同构解析逻辑收敛于此，路由只做参数编排。
"""

from __future__ import annotations

import os
import re
from datetime import datetime

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)

_LOG_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)"
)


def _parse_log_line(line: str) -> dict | None:
    """解析单行日志；不匹配行格式时返回 None。"""
    match = _LOG_PATTERN.match(line)
    if not match:
        return None
    timestamp_str, source, level, message = match.groups()
    try:
        iso_timestamp = datetime.strptime(
            timestamp_str, "%Y-%m-%d %H:%M:%S,%f"
        ).isoformat()
    except ValueError:
        # 时间戳解析失败属已知降级路径：保留原始字符串并记录，不再静默。
        logger.debug("日志时间戳解析失败，原样保留: %s", timestamp_str)
        iso_timestamp = timestamp_str
    return {
        "timestamp": iso_timestamp,
        "level": level.lower(),
        "message": message.strip(),
        "source": source.strip(),
    }


def _read_recent_lines(limit: int, multiplier: int | None = 3) -> list[str]:
    """读取日志文件去空白行；multiplier 为 None 时全量读取，否则取尾部 limit*multiplier 行。"""
    log_file = Config.LOG_FILE
    if not os.path.exists(log_file):
        return []
    with open(log_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    if multiplier is None:
        return lines
    return lines[-(limit * multiplier):]


def query_system_logs(
    limit: int = 100,
    level_filter: str = "",
    search: str = "",
    date_filter: str = "",
    task_id_filter: str = "",
) -> list[dict]:
    """按级别/关键字/日期/任务 ID 过滤系统日志，倒序返回最近 limit 条。"""
    parsed_logs: list[dict] = []
    for line in _read_recent_lines(limit, multiplier=3):
        entry = _parse_log_line(line)
        if entry is None:
            parsed_logs.append(
                {"timestamp": "", "level": "info", "message": line, "source": "unknown"}
            )
            continue
        if level_filter and entry["level"] != level_filter.lower():
            continue
        if search and search.lower() not in entry["message"].lower():
            continue
        if date_filter and not entry["timestamp"].startswith(date_filter):
            continue
        if task_id_filter:
            task_pattern = f"[Task-{task_id_filter[:8]}]"
            if (
                task_pattern not in entry["message"]
                and task_id_filter not in entry["message"]
            ):
                continue
        parsed_logs.append(entry)

    parsed_logs.reverse()
    return parsed_logs[:limit]


def query_latest_logs(since: str = "", limit: int = 50) -> list[dict]:
    """返回 since（ISO 时间戳，含）之后的最新日志，按时间升序取尾部 limit 条。"""
    latest: list[dict] = []
    for line in _read_recent_lines(limit, multiplier=2):
        entry = _parse_log_line(line)
        if entry is None:
            continue
        if since and entry["timestamp"] <= since:
            continue
        latest.append(entry)

    latest.sort(key=lambda item: item["timestamp"])
    return latest[-limit:]


def query_task_system_logs(task_id: str, limit: int = 200, level_filter: str = "") -> list[dict]:
    """提取与指定任务相关的系统日志（全文件扫描，按时间升序取尾部 limit 条）。"""
    task_patterns = [f"[Task-{task_id[:8]}]", f"任务 {task_id}", task_id]
    task_logs: list[dict] = []
    for line in _read_recent_lines(limit, multiplier=None):
        if not any(pattern in line for pattern in task_patterns):
            continue
        entry = _parse_log_line(line)
        if entry is None:
            continue
        entry["task_id"] = task_id
        if level_filter and entry["level"] != level_filter.lower():
            continue
        task_logs.append(entry)

    task_logs.sort(key=lambda item: item["timestamp"])
    return task_logs[-limit:]
