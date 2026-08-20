import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.extensions import db
from app.models import GoogleSheetToken, GoogleSheetTokenTaskType, Task
from app.repositories.google_sheet_token_repository import GoogleSheetTokenRepository
from app.repositories.sdk_client import SdkFilterUnavailableError
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)

RANDOM_TOKEN_VALUE = "__random__"


class GoogleSheetTokenService:
    def __init__(self, repository: GoogleSheetTokenRepository | None = None):
        """注入 Token 远程 CRUD 仓储；运行态占用逻辑仍使用本地 ORM。"""
        self._repository = repository or GoogleSheetTokenRepository()

    @staticmethod
    def _normalize_token_task_type(task_type: Optional[str], default: Optional[str] = GoogleSheetTokenTaskType.GOOGLE_SHEET.value) -> Optional[str]:
        """将 Token 适用任务类型归一为系统枚举值。"""
        return GoogleSheetTokenTaskType.normalize(task_type, default=default)

    def _build_live_usage_snapshot(self):
        """统计运行任务使用的 Token 数和全局实时占用总数。"""
        # TODO: 运行任务筛选依赖 ParamTasks/Query，禁止 SDK 全表筛选。
        token_usage: Dict[int, int] = {}
        current_total = 0

        running_tasks = Task.query.filter_by(status='running').all()
        for task in running_tasks:
            try:
                config = json.loads(task.config) if isinstance(task.config, str) else (task.config or {})
            except Exception:
                continue

            if not isinstance(config, dict):
                continue
            if config.get("token_type", "file") != "file":
                continue

            token_id = config.get("token_id")
            if not token_id:
                continue

            token_id_int = int(token_id)
            token_usage[token_id_int] = int(token_usage.get(token_id_int, 0)) + 1
            current_total += 1

        return {
            "token_usage": token_usage,
            "current_total": current_total,
        }

    def _assert_token_usage_available(self, token: GoogleSheetToken, current_in_use: int):
        """校验指定 Token 已启用且未超过自身并发占用上限。"""
        if not token:
            raise ValueError("所选 Token 不存在")
        if not token.is_active:
            raise ValueError(f"Token [{token.name}] 已被禁用，请更换 Token")

        max_usage = int(token.max_usage_count or 0)
        if max_usage > 0 and int(current_in_use) >= max_usage:
            raise ValueError(
                f"Token [{token.name}] 已达到最大占用次数 ({current_in_use}/{max_usage})，请更换 Token"
            )

    def reconcile_in_use_counts(self):
        """按当前运行态快照校正远端 Token 的实时占用计数。"""
        snapshot = self._build_live_usage_snapshot()
        token_usage = snapshot["token_usage"]

        tokens = GoogleSheetToken.query.all()
        for token in tokens:
            token.current_in_use_count = int(token_usage.get(int(token.id), 0))

        db.session.commit()

    def list_tokens(self, task_type: Optional[str] = None):
        """读取 Token 列表。

        无筛选列表可直接走远程 CRUD；SDK 尚未声明 ``task_type`` 筛选能力，
        因此拒绝在本进程拉取全量数据后筛选，以避免结果不完整或性能失控。
        """
        if task_type is None:
            return self._repository.list_public()
        raise SdkFilterUnavailableError(
            "远程 Token 列表接口未声明 task_type 筛选能力，请先补充服务端接口"
        )

    def get_token(self, token_id: int, include_context: bool = False):
        """通过远程 CRUD 读取单个 Token，并按需返回敏感凭据内容。"""
        token = self._repository.get(int(token_id))
        if not token:
            raise ValueError("所选 Token 不存在")
        return self._repository.public_record(token, include_context=include_context)

    def import_token(
        self,
        token_context: Optional[str] = None,
        name: Optional[str] = None,
        max_usage_count: Optional[int] = None,
        token_file: Optional[str] = None,
        task_type: Optional[str] = None,
    ):
        """导入 Token 内容并创建或更新可用的 Token 注册记录。"""
        normalized_task_type = self._normalize_token_task_type(task_type)
        normalized_context = self._load_token_context(token_context=token_context, token_file=token_file)
        token = GoogleSheetToken.query.filter_by(
            token_context=normalized_context,
            task_type=normalized_task_type,
        ).first()
        is_new = token is None

        if token is None:
            token = GoogleSheetToken(
                name=(name or "").strip() or self._build_default_name(),
                task_type=normalized_task_type,
                token_file="",
                token_context=normalized_context,
                max_usage_count=max(0, int(max_usage_count or 0)),
                is_active=True,
            )
            db.session.add(token)
            db.session.flush()
            token.token_file = self._build_runtime_token_file(token.id)
        else:
            token.name = (name or "").strip() or token.name or self._build_default_name(token.id)
            token.task_type = normalized_task_type
            token.token_context = normalized_context
            token.is_active = True
            if max_usage_count is not None:
                token.max_usage_count = max(0, int(max_usage_count))
            if not token.token_file:
                db.session.flush()
                token.token_file = self._build_runtime_token_file(token.id)

        db.session.flush()
        self.ensure_token_file(token)
        db.session.commit()

        logger.info("Imported Google Sheet token successfully: %s", token.name)
        return token.to_dict(), is_new

    def update_token(self, token_id: int, **payload):
        """通过远程 CRUD 更新 Token 的常规字段。

        导入仍留在本地：它同时承担凭据文件创建与重复检测。此方法仅服务于
        详情页常规更新，不修改运行态占用次数和历史使用次数。
        """
        token = self._repository.get(int(token_id))
        if not token:
            raise ValueError("所选 Token 不存在")

        if payload.get("name") is not None:
            token["name"] = str(payload["name"]).strip() or token.get("name")
        if payload.get("max_usage_count") is not None:
            token["max_usage_count"] = max(0, int(payload["max_usage_count"]))
        if payload.get("is_active") is not None:
            token["is_active"] = bool(payload["is_active"])
        if payload.get("task_type") is not None:
            token["task_type"] = self._normalize_token_task_type(payload["task_type"])
        # 只有凭据内容确有变更时才同步本地运行时文件，避免无意义文件写入。
        token_context_changed = payload.get("token_context") is not None
        if token_context_changed:
            token["token_context"] = self._load_token_context(
                token_context=payload["token_context"]
            )

        if not token.get("token_file"):
            token["token_file"] = self._build_runtime_token_file(token["id"])
        if token_context_changed:
            self._ensure_token_file_payload(token)
        saved = self._repository.save(token)
        return self._repository.public_record(saved)

    def _ensure_token_file_payload(self, token: Dict[str, Any]) -> str:
        """将远端 DTO 中的凭据内容同步到任务运行所需的本地文件。"""
        runtime_path = Path(token.get("token_file") or self._build_runtime_token_file(token["id"]))
        if not runtime_path.is_absolute():
            runtime_path = Path.cwd() / runtime_path
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path_str = str(runtime_path.relative_to(Path.cwd())).replace("\\", "/")
        token["token_file"] = runtime_path_str
        token_context = str(token.get("token_context") or "")
        if token_context and (
            not runtime_path.exists() or runtime_path.read_text(encoding="utf-8") != token_context
        ):
            runtime_path.write_text(token_context, encoding="utf-8")
        return runtime_path_str

    def get_usage_summary(self):
        """返回 Token 池的实时占用和历史使用汇总。"""
        # 当前占用与历史使用次数语义不同，分别从本地运行态统计。
        self.reconcile_in_use_counts()
        global_max_usage = self._get_global_max_usage()
        current_total = db.session.query(
            db.func.coalesce(db.func.sum(GoogleSheetToken.current_in_use_count), 0)
        ).scalar() or 0
        total_usage = db.session.query(
            db.func.coalesce(db.func.sum(GoogleSheetToken.task_usage_count), 0)
        ).scalar() or 0
        active_count = GoogleSheetToken.query.filter_by(is_active=True).count()
        available_count = sum(
            1 for token in GoogleSheetToken.query.filter_by(is_active=True).all() if token.is_available()
        )
        return {
            "current_total_in_use": int(current_total),
            "current_total_usage": int(total_usage),
            "global_max_usage": int(global_max_usage),
            "active_token_count": int(active_count),
            "available_token_count": int(available_count),
        }

    def prepare_task_config(self, config: Dict[str, Any]):
        """补全任务配置中的 Token 信息，供创建流程统一使用。"""
        if not isinstance(config, dict):
            return config

        token_type = config.get("token_type", "file")
        if token_type != "file":
            return config

        self._assert_global_usage_available()

        token_selection = config.get("token_id")
        if token_selection in (None, "", 0, "0"):
            return config

        token_task_type = self._normalize_token_task_type(config.get("token_task_type"))
        token = self._pick_token(token_selection, task_type=token_task_type)
        token_file = self.ensure_token_file(token)

        resolved = dict(config)
        resolved["token_id"] = token.id
        resolved["token_file"] = token_file
        resolved["token_name"] = token.name
        if token_selection == RANDOM_TOKEN_VALUE:
            resolved["token_selection_mode"] = RANDOM_TOKEN_VALUE
        return resolved

    def validate_task_start(self, config: Dict[str, Any]):
        """在任务启动前校验指定 Token 是否存在、启用且可用。"""
        if not isinstance(config, dict):
            return

        token_type = config.get("token_type", "file")
        if token_type != "file":
            return

        snapshot = self._build_live_usage_snapshot()
        self._assert_global_usage_available(current_total=snapshot["current_total"])

        token_id = config.get("token_id")
        if not token_id:
            return

        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("所选 Token 不存在")
        expected_task_type = self._normalize_token_task_type(config.get("token_task_type"))
        actual_task_type = token.task_type or GoogleSheetTokenTaskType.GOOGLE_SHEET.value
        if expected_task_type and actual_task_type != expected_task_type:
            raise ValueError(f"Token [{token.name}] 不适用于当前任务类型")
        current_in_use = int(snapshot["token_usage"].get(int(token.id), 0))
        self._assert_token_usage_available(token, current_in_use)

    def increment_usage(self, token_id: Optional[int]):
        """为启动的任务增加 Token 实时占用，并返回运行时文件路径。"""
        if not token_id:
            return None

        snapshot = self._build_live_usage_snapshot()
        self._assert_global_usage_available(current_total=snapshot["current_total"])

        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("所选 Token 不存在")
        current_in_use = int(snapshot["token_usage"].get(int(token.id), 0))
        self._assert_token_usage_available(token, current_in_use)

        token.task_usage_count = int(token.task_usage_count or 0) + 1
        token.current_in_use_count = current_in_use + 1
        token.last_used_at = datetime.now()
        db.session.commit()
        return token

    def release_usage(self, token_id: Optional[int]):
        """在任务结束后释放 Token 实时占用。"""
        if not token_id:
            return None

        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            return None

        token.current_in_use_count = max(0, int(token.current_in_use_count or 0) - 1)
        token.last_used_at = datetime.now()
        db.session.commit()
        return token

    def _load_token_context(self, token_context: Optional[str] = None, token_file: Optional[str] = None):
        """从请求内容或本地文件读取并校验 Token 凭据文本。"""
        raw_context = (token_context or "").strip()
        if not raw_context and token_file:
            token_path = Path(token_file)
            if not token_path.is_absolute():
                token_path = Path.cwd() / token_path
            if not token_path.exists():
                raise ValueError(f"token文件不存在: {token_file}")
            raw_context = token_path.read_text(encoding="utf-8")

        if not raw_context:
            raise ValueError("token内容不能为空")

        try:
            parsed = json.loads(raw_context)
        except json.JSONDecodeError as exc:
            raise ValueError(f"token内容不是有效JSON: {exc}") from exc

        return json.dumps(parsed, ensure_ascii=False, indent=2)

    def ensure_token_file(self, token: GoogleSheetToken):
        """确保 Token 内容已写入任务可读取的本地运行时文件。"""
        runtime_path = Path(token.token_file or self._build_runtime_token_file(token.id))
        if not runtime_path.is_absolute():
            runtime_path = Path.cwd() / runtime_path

        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path_str = str(runtime_path.relative_to(Path.cwd())).replace("\\", "/")
        if token.token_file != runtime_path_str:
            token.token_file = runtime_path_str
            db.session.flush()

        if not runtime_path.exists() or runtime_path.read_text(encoding="utf-8") != token.token_context:
            runtime_path.write_text(token.token_context, encoding="utf-8")

        return runtime_path_str

    def _pick_token(self, token_selection: Any, task_type: Optional[str] = None):
        """按显式选择或随机策略挑选当前可用 Token。"""
        snapshot = self._build_live_usage_snapshot()
        normalized_task_type = self._normalize_token_task_type(task_type)
        if str(token_selection) == RANDOM_TOKEN_VALUE:
            return self._pick_random_available_token(snapshot=snapshot, task_type=normalized_task_type)

        token = GoogleSheetToken.query.get(int(token_selection))
        if not token:
            raise ValueError("所选 Token 不存在")
        actual_task_type = token.task_type or GoogleSheetTokenTaskType.GOOGLE_SHEET.value
        if normalized_task_type and actual_task_type != normalized_task_type:
            raise ValueError(f"Token [{token.name}] 不属于 {normalized_task_type} 分组")
        current_in_use = int(snapshot["token_usage"].get(int(token.id), 0))
        self._assert_token_usage_available(token, current_in_use)
        return token

    def _pick_random_available_token(self, snapshot: Optional[Dict[str, Any]] = None, task_type: Optional[str] = None):
        """从适用且未满额的 Token 中随机选择一个。"""
        snapshot = snapshot or self._build_live_usage_snapshot()
        token_usage = snapshot["token_usage"]
        normalized_task_type = self._normalize_token_task_type(task_type)
        tokens = GoogleSheetToken.query.filter_by(
            is_active=True,
            task_type=normalized_task_type,
        ).order_by(
            GoogleSheetToken.current_in_use_count.asc(),
            GoogleSheetToken.task_usage_count.asc(),
            GoogleSheetToken.id.asc(),
        ).all()
        available = []
        for token in tokens:
            current_in_use = int(token_usage.get(int(token.id), 0))
            max_usage = int(token.max_usage_count or 0)
            if max_usage <= 0 or current_in_use < max_usage:
                available.append((token, current_in_use))
        if not available:
            raise ValueError(
                "所有 Token 都已达到上限，请先调整 Token 或系统上限配置"
            )

        min_usage = min(current_in_use for _, current_in_use in available)
        candidates = [token for token, current_in_use in available if current_in_use == min_usage]
        return random.choice(candidates)

    def _assert_global_usage_available(self, current_total: Optional[int] = None):
        """校验全局 Token 实时占用未超过系统总上限。"""
        max_usage = self._get_global_max_usage()
        if max_usage <= 0:
            return

        if current_total is None:
            current_total = db.session.query(
                db.func.coalesce(db.func.sum(GoogleSheetToken.current_in_use_count), 0)
            ).scalar() or 0
        if int(current_total) >= max_usage:
            raise ValueError(
                f"所有 Token 当前占用次数已达到系统上限({max_usage})，停止生成任务"
            )

    def _get_global_max_usage(self):
        """读取并解析系统配置中的 Token 全局并发上限。"""
        value = get_config_manager().get_config("google_sheet_token_global_max_usage", 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _build_default_name(token_id: Optional[int] = None):
        """根据可选 Token 主键生成默认显示名称。"""
        return f"Google Token #{int(token_id)}" if token_id else "Google Token"

    @staticmethod
    def _build_runtime_token_file(token_id: int):
        """生成 Token 凭据在本地运行目录中的标准文件路径。"""
        return f"data/google_sheet_tokens/token_{int(token_id)}.json"


google_sheet_token_service = GoogleSheetTokenService()


def get_google_sheet_token_service():
    """返回共享的 Google Sheet Token 服务实例。"""
    return google_sheet_token_service
