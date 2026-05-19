"""Download every backtest global-preview Excel workbook from a running site.

默认指向线上地址 http://172.18.20.17:5001，可通过 --base-url 覆盖。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_BASE_URL = "http://172.18.20.17:5001"
XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class BacktestTask:
    id: str
    name: str
    status: str
    created_at: str


@dataclass(frozen=True)
class DownloadResult:
    task_id: str
    ok: bool
    path: Path | None = None
    error: str = ""


def normalize_base_url(raw_url: str) -> str:
    value = (raw_url or DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"无效 base-url: {raw_url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def build_session(timeout: float, retries: int) -> requests.Session:
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "backtest-global-preview-downloader/1.0"})
    session.request_timeout = timeout  # type: ignore[attr-defined]
    return session


def request_json(session: requests.Session, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    timeout = getattr(session, "request_timeout", 30.0)
    response = session.request(method, url, timeout=timeout, **kwargs)
    if response.status_code == 401:
        raise RuntimeError("认证失败：请提供 --username/--password 或 --access-token")
    if response.status_code == 403:
        raise RuntimeError(f"权限不足：{response.text[:300]}")
    response.raise_for_status()
    try:
        return response.json()
    except json.JSONDecodeError as err:
        raise RuntimeError(f"接口未返回 JSON: {url}") from err


def login(session: requests.Session, base_url: str, username: str, password: str) -> str:
    url = urljoin(base_url, "/api/auth/login")
    payload = request_json(
        session,
        "POST",
        url,
        json={"username": username, "password": password},
    )
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("message") or "登录失败")
    token = ((payload.get("data") or {}).get("access_token") or "").strip()
    if not token:
        raise RuntimeError("登录成功响应中没有 access_token")
    return token


def configure_auth(session: requests.Session, base_url: str, args: argparse.Namespace) -> None:
    token = (args.access_token or os.environ.get("BACKTEST_ACCESS_TOKEN") or "").strip()
    username = (args.username or os.environ.get("BACKTEST_USERNAME") or "").strip()
    password = args.password or os.environ.get("BACKTEST_PASSWORD") or ""

    if not token and username and password:
        token = login(session, base_url, username, password)

    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})


def parse_datetime(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone().replace(tzinfo=None)


def list_backtest_tasks(
    session: requests.Session,
    base_url: str,
    per_page: int,
    status: str | None,
    keyword: str,
    max_pages: int | None,
    created_after: datetime | None,
) -> list[BacktestTask]:
    tasks: list[BacktestTask] = []
    page = 1

    while True:
        params: dict[str, Any] = {
            "task_type": "backtest_training",
            "page": page,
            "per_page": per_page,
        }
        if status:
            params["status"] = status
        if keyword:
            params["keyword"] = keyword

        payload = request_json(session, "GET", urljoin(base_url, "/api/tasks"), params=params)
        should_stop = False
        for item in payload.get("tasks") or []:
            task_id = str(item.get("id") or "").strip()
            if not task_id:
                continue
            created_at = str(item.get("created_at") or "")
            created_time = parse_datetime(created_at)
            if created_after is not None and created_time is not None and created_time < created_after:
                should_stop = True
                continue
            tasks.append(
                BacktestTask(
                    id=task_id,
                    name=str(item.get("name") or task_id),
                    status=str(item.get("status") or ""),
                    created_at=created_at,
                )
            )

        pagination = payload.get("pagination") or {}
        has_next = bool(pagination.get("has_next"))
        if should_stop or not has_next:
            break
        if max_pages is not None and page >= max_pages:
            break
        page += 1

    return tasks


def parse_filename_from_content_disposition(value: str) -> str:
    if not value:
        return ""

    filename_star = re.search(r"filename\*=UTF-8''([^;]+)", value, flags=re.IGNORECASE)
    if filename_star:
        return unquote(filename_star.group(1).strip().strip('"'))

    filename = re.search(r'filename="?([^";]+)"?', value, flags=re.IGNORECASE)
    if filename:
        return filename.group(1).strip()

    return ""


def safe_filename(name: str, fallback: str) -> str:
    raw = (name or fallback).strip() or fallback
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", raw).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:180] or fallback


def strip_global_preview_suffix(filename: str) -> str:
    path = Path(filename)
    stem = re.sub(r"_global_preview$", "", path.stem, flags=re.IGNORECASE)
    return f"{stem}{path.suffix or '.xlsx'}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10_000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法生成不重复文件名: {path}")


def download_global_preview(
    session: requests.Session,
    base_url: str,
    task: BacktestTask,
    output_dir: Path,
    overwrite: bool,
) -> DownloadResult:
    url = urljoin(base_url, f"/backtest-training/api/global-preview/{task.id}/export")
    timeout = getattr(session, "request_timeout", 30.0)

    try:
        response = session.get(url, timeout=timeout)
        if response.status_code == 401:
            return DownloadResult(task_id=task.id, ok=False, error="认证失败")
        if response.status_code == 403:
            return DownloadResult(task_id=task.id, ok=False, error="权限不足")
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if XLSX_MIMETYPE not in content_type and not response.content.startswith(b"PK"):
            return DownloadResult(
                task_id=task.id,
                ok=False,
                error=f"响应不是 xlsx: content-type={content_type}, body={response.text[:200]}",
            )

        header_filename = parse_filename_from_content_disposition(
            response.headers.get("Content-Disposition", "")
        )
        fallback_name = f"{task.name or task.id}.xlsx"
        filename = safe_filename(header_filename or fallback_name, f"{task.id}.xlsx")
        filename = strip_global_preview_suffix(filename)
        if not filename.lower().endswith(".xlsx"):
            filename = f"{filename}.xlsx"

        path = output_dir / filename
        if not overwrite:
            path = unique_path(path)
        path.write_bytes(response.content)
        return DownloadResult(task_id=task.id, ok=True, path=path)
    except requests.RequestException as err:
        return DownloadResult(task_id=task.id, ok=False, error=str(err))


def write_manifest(output_dir: Path, tasks: list[BacktestTask], results: list[DownloadResult]) -> None:
    by_task_id = {result.task_id: result for result in results}
    rows = []
    for task in tasks:
        result = by_task_id.get(task.id)
        rows.append(
            {
                "task_id": task.id,
                "task_name": task.name,
                "task_status": task.status,
                "created_at": task.created_at,
                "downloaded": bool(result and result.ok),
                "path": str(result.path) if result and result.path else "",
                "error": result.error if result else "未处理",
            }
        )
    (output_dir / "manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量下载回测任务的全局预览页 Excel 文件。",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BACKTEST_BASE_URL", DEFAULT_BASE_URL),
        help=f"站点地址，默认: {DEFAULT_BASE_URL}",
    )
    parser.add_argument("--username", help="登录用户名；也可用 BACKTEST_USERNAME")
    parser.add_argument("--password", help="登录密码；也可用 BACKTEST_PASSWORD")
    parser.add_argument("--access-token", help="浏览器 localStorage 里的 access_token；也可用 BACKTEST_ACCESS_TOKEN")
    parser.add_argument(
        "--output-dir",
        default="downloads/backtest_global_previews",
        help="下载目录，默认: downloads/backtest_global_previews/<时间戳>",
    )
    parser.add_argument("--per-page", type=int, default=100, help="任务分页大小，默认 100")
    parser.add_argument("--status", help="只下载指定状态任务，例如 completed；默认下载全部回测任务")
    parser.add_argument("--keyword", default="", help="按任务列表 keyword 过滤")
    parser.add_argument("--days", type=int, default=7, help="只下载最近 N 天创建的任务，默认 7；传 0 表示不过滤")
    parser.add_argument("--max-pages", type=int, help="最多扫描多少页，调试用")
    parser.add_argument("--timeout", type=float, default=60.0, help="单次请求超时秒数，默认 60")
    parser.add_argument("--retries", type=int, default=3, help="网络重试次数，默认 3")
    parser.add_argument("--overwrite", action="store_true", help="同名文件存在时覆盖")
    parser.add_argument("--dry-run", action="store_true", help="只列出任务，不下载")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = normalize_base_url(args.base_url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    session = build_session(timeout=args.timeout, retries=args.retries)
    configure_auth(session, base_url, args)

    started_at = time.monotonic()
    print(f"站点: {base_url}")
    print(f"下载目录: {output_dir.resolve()}")

    created_after = None
    if args.days and args.days > 0:
        created_after = datetime.now() - timedelta(days=args.days)
        print(f"时间过滤: 仅下载 {created_after:%Y-%m-%d %H:%M:%S} 之后创建的任务")

    tasks = list_backtest_tasks(
        session=session,
        base_url=base_url,
        per_page=max(1, min(args.per_page, 500)),
        status=args.status,
        keyword=args.keyword.strip(),
        max_pages=args.max_pages,
        created_after=created_after,
    )
    print(f"找到 {len(tasks)} 个回测任务")

    if args.dry_run:
        for task in tasks:
            print(f"- {task.id} | {task.status} | {task.name}")
        return 0

    results: list[DownloadResult] = []
    for index, task in enumerate(tasks, start=1):
        print(f"[{index}/{len(tasks)}] 下载 {task.id} {task.name}")
        result = download_global_preview(
            session=session,
            base_url=base_url,
            task=task,
            output_dir=output_dir,
            overwrite=args.overwrite,
        )
        results.append(result)
        if result.ok:
            print(f"  OK: {result.path}")
        else:
            print(f"  FAIL: {result.error}", file=sys.stderr)

    write_manifest(output_dir, tasks, results)
    ok_count = sum(1 for result in results if result.ok)
    fail_count = len(results) - ok_count
    elapsed = time.monotonic() - started_at
    print(f"完成: 成功 {ok_count}, 失败 {fail_count}, 用时 {elapsed:.1f}s")
    print(f"清单: {(output_dir / 'manifest.json').resolve()}")
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
