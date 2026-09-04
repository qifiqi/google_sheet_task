"""Task operation commands for DingTalk messages."""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlparse

from app import create_app
from app.repositories.task_repository import TaskRepository
from app.services.task import task_manager

from ding_stream_service.message_format import build_markdown_message


logger = logging.getLogger(__name__)
_task_repository = TaskRepository()

RESTART_ACTION_RE = re.compile(r"(?:断点重启|重启任务|任务重启|重启|restart)", re.I)
RESTART_ERROR_TASKS_RE = re.compile(
    r"(?:重启异常任务|重启错误任务|重启失败任务|restart\s+error\s+tasks)",
    re.I,
)
TASK_ID_FIELD_RE = re.compile(
    r"(?:任务\s*ID|task[_\s-]*id|taskId)\*{0,2}\s*[：:]\s*`?([A-Za-z0-9_-]{1,64})",
    re.I,
)
TASK_NAME_FIELD_RE = re.compile(r"(?:任务名称|任务名|task\s*name)\*{0,2}\s*[：:]\s*(.+)", re.I)
DIRECT_RESTART_RE = re.compile(
    r"^\s*(?:断点重启|重启任务|任务重启|重启|restart)\s*(?:任务)?\s*(.+?)\s*$",
    re.I | re.S,
)
INDEX_RESTART_RE = re.compile(r"^\s*(?:重启第?\s*(\d+)\s*个?|重启\s*(\d+))\s*$", re.I)
RUNNING_TASK_RE = re.compile(r"(?:查看)?(?:当前)?(?:运行中|运行)(?:的)?(?:任务|项目)", re.I)
STOPPED_TASK_RE = re.compile(r"(?:查看)?(?:停止|已停止|结束)(?:的)?(?:任务|项目)", re.I)
PAGE_RE = re.compile(r"第\s*(\d+)\s*页")
PER_PAGE_RE = re.compile(r"每页\s*(\d+)\s*(?:条|个)?")
LIMIT_RE = re.compile(r"(?:数量|最多|前)\s*(\d+)\s*(?:条|个)?")
STOPPED_STATUSES = ["completed", "cancelled", "error",'pending']
DEFAULT_BATCH_RESTART_LIMIT = 5
MAX_BATCH_RESTART_LIMIT = 20
LIST_CACHE_TTL_SECONDS = 600


@dataclass(frozen=True)
class ParsedRestartCommand:
    target: str
    target_type: Literal["id", "name"]
    resume_from_checkpoint: bool = True
    source: Literal["direct", "cached_index"] = "direct"


@dataclass(frozen=True)
class ParsedListCommand:
    status_group: Literal["running", "stopped"]
    page: int = 1
    per_page: int = 5


@dataclass(frozen=True)
class ParsedBatchRestartCommand:
    status: Literal["error"] = "error"
    limit: int = DEFAULT_BATCH_RESTART_LIMIT
    resume_from_checkpoint: bool = True


@dataclass(frozen=True)
class TaskCommandResult:
    handled: bool
    message: str = ""


class TaskCommandService:
    """Execute platform task commands from the DingTalk microservice."""

    def __init__(self):
        self._app = None
        self._app_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._list_cache: dict[str, tuple[float, list[dict]]] = {}

    def handle_message(
        self,
        text: str,
        sender_nick: str,
        conversation_id: str = "default",
    ) -> TaskCommandResult:
        batch_restart_command = parse_batch_restart_command(text)
        if batch_restart_command:
            logger.info(
                "识别到组合重启指令: sender=%s status=%s limit=%s",
                sender_nick,
                batch_restart_command.status,
                batch_restart_command.limit,
            )
            try:
                result = self.restart_error_tasks(batch_restart_command)
            except Exception as exc:
                logger.exception("执行钉钉异常任务重启指令失败: %s", exc)
                result = {"status": "error", "message": str(exc)}
            return TaskCommandResult(
                handled=True,
                message=format_batch_restart_reply(result, batch_restart_command, sender_nick),
            )

        list_command = parse_list_command(text)
        if list_command:
            logger.info(
                "识别到任务查询指令: sender=%s status_group=%s page=%s per_page=%s",
                sender_nick,
                list_command.status_group,
                list_command.page,
                list_command.per_page,
            )
            try:
                result = self.list_tasks(list_command)
                self.cache_list_result(conversation_id, result.get("tasks") or [])
            except Exception as exc:
                logger.exception("执行钉钉任务查询指令失败: %s", exc)
                result = {"status": "error", "message": str(exc)}
            return TaskCommandResult(
                handled=True,
                message=format_list_reply(result, list_command, sender_nick),
            )

        restart_command = self.parse_cached_index_restart_command(text, conversation_id)
        if not restart_command:
            restart_command = parse_restart_command(text)
        if not restart_command:
            return TaskCommandResult(handled=False)

        logger.info(
            "识别到单任务重启指令: sender=%s target_type=%s target=%s",
            sender_nick,
            restart_command.target_type,
            restart_command.target,
        )
        try:
            result = self.restart_task(restart_command)
        except Exception as exc:
            logger.exception("执行钉钉任务指令失败: %s", exc)
            result = {"status": "error", "message": str(exc)}
        return TaskCommandResult(
            handled=True,
            message=format_restart_reply(result, sender_nick),
            )

    def cache_list_result(self, conversation_id: str, tasks: list[dict]) -> None:
        key = _cache_key(conversation_id)
        with self._cache_lock:
            self._list_cache[key] = (time.time(), tasks)
        logger.info(
            "缓存任务查询结果: conversation_id=%s count=%s ttl_seconds=%s",
            key,
            len(tasks),
            LIST_CACHE_TTL_SECONDS,
        )

    def parse_cached_index_restart_command(
        self,
        text: str,
        conversation_id: str,
    ) -> ParsedRestartCommand | None:
        index = parse_cached_restart_index(text)
        if index is None:
            return None

        key = _cache_key(conversation_id)
        with self._cache_lock:
            cached = self._list_cache.get(key)

        if not cached:
            logger.warning("未找到任务查询缓存: conversation_id=%s index=%s", key, index)
            return ParsedRestartCommand(
                target=f"最近查询结果已过期，请先发送“查看停止任务”或“查看运行任务”（序号 {index}）",
                target_type="name",
                source="cached_index",
            )

        cached_at, tasks = cached
        if time.time() - cached_at > LIST_CACHE_TTL_SECONDS:
            with self._cache_lock:
                self._list_cache.pop(key, None)
            logger.warning("任务查询缓存已过期: conversation_id=%s index=%s", key, index)
            return ParsedRestartCommand(
                target=f"最近查询结果已过期，请先发送“查看停止任务”或“查看运行任务”（序号 {index}）",
                target_type="name",
                source="cached_index",
            )

        if index < 1 or index > len(tasks):
            logger.warning(
                "任务查询缓存序号越界: conversation_id=%s index=%s count=%s",
                key,
                index,
                len(tasks),
            )
            return ParsedRestartCommand(
                target=f"序号 {index} 不在最近查询结果中，请重新查询后选择",
                target_type="name",
                source="cached_index",
            )

        task = tasks[index - 1]
        task_id = str(task.get("id") or "").strip()
        if not task_id:
            return None
        logger.info(
            "通过查询缓存解析重启序号: conversation_id=%s index=%s task_id=%s",
            key,
            index,
            task_id,
        )
        return ParsedRestartCommand(
            target=task_id,
            target_type="id",
            source="cached_index",
        )

    def restart_error_tasks(self, command: ParsedBatchRestartCommand) -> dict:
        app = self._get_app()
        with app.app_context():
            # Batch restart is intentionally capped to avoid resurrecting a large
            # backlog of historical failures from a single DingTalk message.
            # SDK 仅支持单字段排序，这里以 updated_at 倒序近似原复合排序。
            page = _task_repository.list_tasks(
                page_index=1,
                page_size=command.limit,
                statuses=[command.status],
                order_field="updated_at",
                order_type="desc",
            )
            tasks = page["items"]
            total = page["total"]
            logger.info(
                "开始批量重启异常任务: status=%s total=%s selected=%s limit=%s",
                command.status,
                total,
                len(tasks),
                command.limit,
            )
            results = []
            for task in tasks:
                task_id = task.id
                task_name = task.name
                task_type = task.task_type
                original_status = task.status
                logger.info(
                    "钉钉组合指令重启异常任务: task_id=%s task_name=%s type=%s",
                    task_id,
                    task_name,
                    task_type,
                )
                restart_result = task_manager.restart_task(
                    task_id,
                    resume_from_checkpoint=command.resume_from_checkpoint,
                )
                logger.info(
                    "异常任务重启结果: task_id=%s restart_status=%s message=%s",
                    task_id,
                    restart_result.get("status"),
                    restart_result.get("message"),
                )
                results.append(
                    {
                        "task_id": task_id,
                        "task_name": task_name,
                        "task_type": task_type,
                        "original_status": original_status,
                        "restart_status": restart_result.get("status"),
                        "message": restart_result.get("message"),
                        "restart_from_step": restart_result.get("restart_from_step"),
                    }
                )

            return {
                "status": "success",
                "target_status": command.status,
                "total": total,
                "processed": len(results),
                "results": results,
            }

    def list_tasks(self, command: ParsedListCommand) -> dict:
        app = self._get_app()
        with app.app_context():
            statuses = (
                ["running"]
                if command.status_group == "running"
                else STOPPED_STATUSES
            )
            page = _task_repository.list_tasks(
                page_index=command.page,
                page_size=command.per_page,
                statuses=statuses,
                order_field="updated_at",
                order_type="desc",
            )
            total = page["total"]
            tasks = page["items"]
            logger.info(
                "查询任务列表: status_group=%s page=%s per_page=%s total=%s",
                command.status_group,
                command.page,
                command.per_page,
                total,
            )
            return {
                "status": "success",
                "total": total,
                "tasks": [
                    {
                        "id": task.id,
                        "name": task.name,
                        "status": task.status,
                        "task_type": task.task_type,
                        "current_step": task.current_step,
                        "total_steps": task.total_steps,
                    }
                    for task in tasks
                ],
            }

    def restart_task(self, command: ParsedRestartCommand) -> dict:
        if command.source == "cached_index" and command.target_type != "id":
            return {"status": "error", "message": command.target}

        app = self._get_app()
        with app.app_context():
            task, error_message = self._resolve_task(command)
            if error_message:
                logger.warning(
                    "单任务重启目标解析失败: target_type=%s target=%s error=%s",
                    command.target_type,
                    command.target,
                    error_message,
                )
                return {"status": "error", "message": error_message}

            task_id = task.id
            task_name = task.name
            task_status = task.status
            task_type = task.task_type
            logger.info(
                "钉钉指令触发任务断点重启: task_id=%s task_name=%s status=%s type=%s",
                task_id,
                task_name,
                task_status,
                task_type,
            )

            result = task_manager.restart_task(
                task_id,
                resume_from_checkpoint=command.resume_from_checkpoint,
            )
            logger.info(
                "单任务重启结果: task_id=%s restart_status=%s message=%s",
                task_id,
                result.get("status"),
                result.get("message"),
            )
            result.update(
                {
                    "task_id": task_id,
                    "task_name": task_name,
                    "task_status": task_status,
                    "task_type": task_type,
                }
            )
            return result

    def _get_app(self):
        if self._app is not None:
            return self._app

        with self._app_lock:
            if self._app is None:
                logger.info("初始化钉钉微服务 Flask app 上下文")
                self._app = create_app()
        return self._app

    def _resolve_task(self, command: ParsedRestartCommand) -> tuple[dict | None, str | None]:
        if command.target_type == "id":
            task = _task_repository.get(command.target)
            if not task:
                return None, f"未找到任务ID: {command.target}"
            return task, None

        # SDK 无精确名称匹配；用服务端 keyword 缩小范围后，在本地做精确名称比对。
        # 只要凑齐两个同名任务即可判定不唯一，无需遍历全部页。
        matches = []
        page_index = 1
        while len(matches) < 2:
            page = _task_repository.list_tasks(
                page_index=page_index,
                page_size=50,
                keyword=command.target,
                order_field="created_at",
                order_type="desc",
            )
            items = page["items"]
            if not items:
                break
            matches.extend(
                item
                for item in items
                if str(item.get("name") or "") == command.target
            )
            if page_index * 50 >= page["total"]:
                break
            page_index += 1

        if not matches:
            return None, f"未找到任务名: {command.target}"
        if len(matches) > 1:
            return None, f"任务名不唯一，请改用任务ID: {command.target}"
        return matches[0], None


def parse_restart_command(text: str) -> ParsedRestartCommand | None:
    normalized_text = _strip_bot_mentions(text)
    if not RESTART_ACTION_RE.search(normalized_text):
        return None

    task_id = extract_task_id(normalized_text)
    if task_id:
        return ParsedRestartCommand(target=task_id, target_type="id")

    task_name = extract_task_name(normalized_text)
    if task_name:
        return ParsedRestartCommand(target=task_name, target_type="name")

    direct_match = DIRECT_RESTART_RE.match(normalized_text)
    if direct_match:
        direct_target = _clean_field_value(direct_match.group(1))
        if direct_target:
            return ParsedRestartCommand(
                target=direct_target,
                target_type="id" if _looks_like_task_id(direct_target) else "name",
            )

    return None


def parse_cached_restart_index(text: str) -> int | None:
    normalized_text = _strip_bot_mentions(text)
    match = INDEX_RESTART_RE.match(normalized_text)
    if not match:
        return None
    raw_index = match.group(1) or match.group(2)
    try:
        index = int(raw_index)
    except (TypeError, ValueError):
        return None
    return index if index > 0 else None


def parse_batch_restart_command(text: str) -> ParsedBatchRestartCommand | None:
    normalized_text = _strip_bot_mentions(text)
    if not normalized_text or not RESTART_ERROR_TASKS_RE.search(normalized_text):
        return None

    return ParsedBatchRestartCommand(
        limit=_extract_positive_int(
            LIMIT_RE,
            normalized_text,
            default=DEFAULT_BATCH_RESTART_LIMIT,
            maximum=MAX_BATCH_RESTART_LIMIT,
        )
    )


def parse_list_command(text: str) -> ParsedListCommand | None:
    normalized_text = _strip_bot_mentions(text)
    if not normalized_text:
        return None

    status_group = None
    if RUNNING_TASK_RE.search(normalized_text):
        status_group = "running"
    elif STOPPED_TASK_RE.search(normalized_text):
        status_group = "stopped"

    if not status_group:
        return None

    return ParsedListCommand(
        status_group=status_group,
        page=_extract_positive_int(PAGE_RE, normalized_text, default=1, maximum=999),
        per_page=_extract_positive_int(PER_PAGE_RE, normalized_text, default=5, maximum=20),
    )


def extract_task_id(text: str) -> str | None:
    field_match = TASK_ID_FIELD_RE.search(text)
    if field_match:
        return _clean_field_value(field_match.group(1))

    url_task_id = _extract_task_id_from_urls(text)
    if url_task_id:
        return url_task_id

    direct_match = DIRECT_RESTART_RE.match(text)
    if direct_match:
        candidate = _clean_field_value(direct_match.group(1)).splitlines()[0].strip()
        if _looks_like_task_id(candidate):
            return candidate

    return None


def extract_task_name(text: str) -> str | None:
    field_match = TASK_NAME_FIELD_RE.search(text)
    if field_match:
        return _clean_field_value(field_match.group(1))
    return None


def format_restart_reply(result: dict, sender_nick: str) -> str:
    task_id = result.get("task_id") or "-"
    task_name = result.get("task_name") or "-"

    if result.get("status") == "success":
        restart_from_step = result.get("restart_from_step")
        start_error = result.get("start_error")
        fields = [
            ("用户", sender_nick),
            ("任务状态", "断点重启已触发"),
            ("任务名称", task_name),
            ("任务ID", task_id),
            ("任务类型", result.get("task_type") or "-"),
            ("原状态", result.get("task_status") or "-"),
        ]
        if restart_from_step is not None:
            fields.append(("断点步骤", restart_from_step))
        if start_error:
            fields.append(("队列提示", start_error))
        return build_markdown_message(
            "任务重启",
            fields,
            summary=result.get("message") or "任务重启成功",
        )

    message = result.get("message") or "任务重启失败"
    return build_markdown_message(
        "任务重启失败",
        [
            ("用户", sender_nick),
            ("任务状态", "断点重启失败"),
            ("任务名称", task_name),
            ("任务ID", task_id),
        ],
        summary=message,
    )


def format_batch_restart_reply(
    result: dict,
    command: ParsedBatchRestartCommand,
    sender_nick: str,
) -> str:
    if result.get("status") != "success":
        return build_markdown_message(
            "异常任务重启失败",
            [
                ("用户", sender_nick),
                ("目标状态", command.status),
                ("单次数量", command.limit),
            ],
            summary=result.get("message") or "未知错误",
        )

    restart_results = result.get("results") or []
    success_count = sum(1 for item in restart_results if item.get("restart_status") == "success")
    failed_count = len(restart_results) - success_count
    fields = [
        ("用户", sender_nick),
        ("目标状态", result.get("target_status") or command.status),
        ("异常任务总数", result.get("total") or 0),
        ("本次处理", result.get("processed") or 0),
        ("重启成功", success_count),
        ("重启失败", failed_count),
        ("单次数量上限", command.limit),
    ]

    if not restart_results:
        return build_markdown_message(
            "异常任务重启",
            fields,
            summary="当前没有需要重启的异常任务。",
        )

    body_lines = []
    for index, item in enumerate(restart_results, start=1):
        status_label = "成功" if item.get("restart_status") == "success" else "失败"
        body_lines.extend(
            [
                f"{index}. **{item.get('task_name') or '-'}**",
                f"   - **结果**：{status_label}",
                f"   - **类型**：{item.get('task_type') or '-'}",
                f"   - **断点步骤**：{item.get('restart_from_step', '-')}",
                f"   - **任务ID**：{item.get('task_id') or '-'}",
                f"   - **说明**：{item.get('message') or '-'}",
            ]
        )

    return build_markdown_message("异常任务重启", fields, body_lines=body_lines)


def format_list_reply(result: dict, command: ParsedListCommand, sender_nick: str) -> str:
    if result.get("status") != "success":
        return build_markdown_message(
            "任务查询失败",
            [
                ("用户", sender_nick),
                ("查询类型", _list_title(command)),
            ],
            summary=result.get("message") or "未知错误",
        )

    total = int(result.get("total") or 0)
    tasks = result.get("tasks") or []
    title = _list_title(command)
    total_pages = max(1, (total + command.per_page - 1) // command.per_page)
    fields = [
        ("用户", sender_nick),
        ("查询类型", title),
        ("当前页", f"{command.page}/{total_pages}"),
        ("每页数量", command.per_page),
        ("总数量", total),
    ]

    if not tasks:
        return build_markdown_message(title, fields, summary="当前没有匹配任务。")

    body_lines = []
    for index, task in enumerate(tasks, start=(command.page - 1) * command.per_page + 1):
        progress = _format_progress(task)
        body_lines.extend(
            [
                f"{index}. **{task['name']}**",
                f"   - **状态**：{task['status']}",
                f"   - **类型**：{task['task_type']}",
                f"   - **进度**：{progress}",
                f"   - **快捷操作**：重启第{index}个",
                "   - **复制重启指令**：",
                f"```text\n重启任务 {task['id']}\n```",
            ]
        )

    if command.page < total_pages:
        next_page = command.page + 1
        keyword = "查看运行任务" if command.status_group == "running" else "查看停止任务"
        body_lines.extend(["", f"> 下一页：{keyword} 第{next_page}页 每页{command.per_page}条"])

    return build_markdown_message(title, fields, body_lines=body_lines)


def _strip_bot_mentions(text: str) -> str:
    return re.sub(r"@[\u4e00-\u9fa5a-zA-Z0-9_]+", "", text or "").strip()


def _clean_field_value(value: str) -> str:
    cleaned = str(value or "").strip()
    cleaned = re.sub(r"\s*\|.*$", "", cleaned)
    cleaned = cleaned.strip("`*：: -\t\r\n")
    return cleaned


def _looks_like_task_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{8,64}", value or ""))


def _extract_task_id_from_urls(text: str) -> str | None:
    for url_match in re.finditer(r"https?://[^\s)>\]]+", text):
        parsed = urlparse(url_match.group(0))
        query = parse_qs(parsed.query)
        task_ids = query.get("task_id") or query.get("taskId")
        if task_ids:
            task_id = _clean_field_value(task_ids[0])
            if task_id:
                return task_id
    return None


def _extract_positive_int(
    pattern: re.Pattern,
    text: str,
    default: int,
    maximum: int,
) -> int:
    match = pattern.search(text)
    if not match:
        return default
    try:
        value = int(match.group(1))
    except ValueError:
        return default
    if value < 1:
        return default
    return min(value, maximum)


def _format_progress(task: dict) -> str:
    current_step = task.get("current_step") or 0
    total_steps = task.get("total_steps") or 0
    if total_steps:
        return f"{current_step}/{total_steps}"
    return "-"


def _list_title(command: ParsedListCommand) -> str:
    return "当前运行任务" if command.status_group == "running" else "已停止任务"


def _cache_key(conversation_id: str) -> str:
    return str(conversation_id or "default").strip() or "default"
