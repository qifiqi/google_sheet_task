from __future__ import annotations

import queue
import threading
from typing import Optional


class TaskRuntimeRegistry:
    """集中管理任务运行态资源。

    这一层只负责线程对象和事件队列的注册、查询、清理，
    让 TaskManager 不再直接维护两份运行态字典。
    """

    def __init__(self) -> None:
        self.running_tasks: dict[str, threading.Thread] = {}
        self.task_events: dict[str, queue.Queue] = {}

    def count_running_tasks(self) -> int:
        """返回当前登记中的运行线程数量。"""
        return len(self.running_tasks)

    def create_task_event_queue(self, task_id: str) -> queue.Queue:
        """为任务创建事件队列并返回。"""
        task_queue: queue.Queue = queue.Queue()
        self.task_events[task_id] = task_queue
        return task_queue

    def get_task_event_queue(self, task_id: str) -> Optional[queue.Queue]:
        """获取任务事件队列。"""
        return self.task_events.get(task_id)

    def has_task_event_queue(self, task_id: str) -> bool:
        """判断任务事件队列是否存在。"""
        return task_id in self.task_events

    def remove_task_event_queue(self, task_id: str) -> None:
        """移除任务事件队列。"""
        self.task_events.pop(task_id, None)

    def register_thread(self, task_id: str, thread: threading.Thread) -> None:
        """登记任务线程。"""
        self.running_tasks[task_id] = thread

    def get_thread(self, task_id: str) -> Optional[threading.Thread]:
        """获取任务线程。"""
        return self.running_tasks.get(task_id)

    def has_thread(self, task_id: str) -> bool:
        """判断任务线程是否存在。"""
        return task_id in self.running_tasks

    def remove_thread(self, task_id: str) -> None:
        """移除任务线程登记。"""
        self.running_tasks.pop(task_id, None)

    def is_task_running(self, task_id: str) -> bool:
        """判断任务线程是否仍处于存活状态。"""
        thread = self.get_thread(task_id)
        return bool(thread and thread.is_alive())

    def clear_task_runtime(self, task_id: str) -> None:
        """一次性清理任务线程和事件队列。"""
        self.remove_thread(task_id)
        self.remove_task_event_queue(task_id)


task_runtime_registry = TaskRuntimeRegistry()
