from app.utils.json_utils import dumps, loads, JSONDecodeError
import random
from datetime import datetime
from typing import Any, Dict, Optional

from app.models import GoogleSheetToken, GoogleSheetTokenTaskType
from app.exceptions import NotFoundError, ValidationError
from app.repositories import google_sheet_token_repository, task_repository
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger
from app.utils.secret_masking import is_masked_token_context, mask_token_context

logger = get_logger(__name__)

RANDOM_TOKEN_VALUE = "__random__"

_TOKEN_PUBLIC_FIELDS = (
    "id",
    "name",
    "task_type",
    "task_usage_count",
    "current_in_use_count",
    "max_usage_count",
    "is_active",
    "last_used_at",
    "created_at",
    "updated_at",
)


def _token_is_available(token) -> bool:
    """token 可用性判定；兼容 ORM 实体与 HTTP 后端的 dict 记录。"""
    is_active = getattr(token, "is_active", None)
    max_usage = int(getattr(token, "max_usage_count", 0) or 0)
    in_use = int(getattr(token, "current_in_use_count", 0) or 0)
    return bool(is_active) and (max_usage <= 0 or in_use < max_usage)


class GoogleSheetTokenService:
    @staticmethod
    def _normalize_token_task_type(task_type: Optional[str], default: Optional[str] = GoogleSheetTokenTaskType.GOOGLE_SHEET.value) -> Optional[str]:
        return GoogleSheetTokenTaskType.normalize(task_type, default=default)

    def _serialize_token(self, token, include_context: bool = False) -> dict[str, Any]:
        """外部输出统一走白名单；token_context 仅在显式请求时返回脱敏预览。"""
        if isinstance(token, dict):
            data = dict(token)
            raw_context = data.pop("token_context", "") or ""
        else:
            data = token.to_dict()
            raw_context = getattr(token, "token_context", "") or ""

        payload = {
            key: data.get(key)
            for key in _TOKEN_PUBLIC_FIELDS
            if key in data
        }
        payload["token_context_size"] = len(raw_context)
        max_usage = int(data.get("max_usage_count") or 0)
        in_use = int(data.get("current_in_use_count") or 0)
        payload["is_available"] = bool(data.get("is_active")) and (
            max_usage <= 0 or in_use < max_usage
        )
        if include_context:
            payload["token_context"] = mask_token_context(raw_context)
        return payload

    def _build_live_usage_snapshot(self):
        token_usage: Dict[int, int] = {}
        current_total = 0

        for row in task_repository.list_id_config_by_status("running"):
            try:
                config = loads(row["config"]) if isinstance(row["config"], str) else (row["config"] or {})
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
        if not token:
            raise NotFoundError("所选 Token 不存在")
        if not token.is_active:
            raise ValidationError(f"Token [{token.name}] 已被禁用，请更换 Token")

        max_usage = int(token.max_usage_count or 0)
        if max_usage > 0 and int(current_in_use) >= max_usage:
            raise ValidationError(
                f"Token [{token.name}] 已达到最大占用次数 ({current_in_use}/{max_usage})，请更换 Token"
            )

    def reconcile_in_use_counts(self):
        """对账并修正 current_in_use_count（写操作）。

        只允许在显式维护路径调用（POST /api/google-sheet-tokens/reconcile、
        启动恢复等）；读路径（list_tokens / get_usage_summary）保持只读，
        占用计数由 acquire/release（increment_usage / release_usage）维护。
        """
        snapshot = self._build_live_usage_snapshot()
        token_usage = snapshot["token_usage"]

        google_sheet_token_repository.apply_in_use_counts(token_usage)

    def list_tokens(self, task_type: Optional[str] = None):
        normalized_task_type = self._normalize_token_task_type(task_type, default=None)
        tokens = google_sheet_token_repository.list_entities_ordered(normalized_task_type)
        return [self._serialize_token(token) for token in tokens]

    def get_token(self, token_id: int, include_context: bool = False):
        token = google_sheet_token_repository.get_entity(int(token_id))
        if not token:
            raise NotFoundError("所选 Token 不存在")
        return self._serialize_token(token, include_context=include_context)

    def import_token(
        self,
        token_context: Optional[str] = None,
        name: Optional[str] = None,
        max_usage_count: Optional[int] = None,
        task_type: Optional[str] = None,
    ):
        normalized_task_type = self._normalize_token_task_type(task_type)
        normalized_context = self._load_token_context(token_context=token_context)
        token = google_sheet_token_repository.get_by_context(
            normalized_context,
            normalized_task_type,
        )
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
            google_sheet_token_repository.add_entity(token)
        else:
            fields = {
                "name": (name or "").strip() or token.name or self._build_default_name(token.id),
                "task_type": normalized_task_type,
                "token_context": normalized_context,
                "is_active": True,
            }
            if max_usage_count is not None:
                fields["max_usage_count"] = max(0, int(max_usage_count))
            google_sheet_token_repository.update_fields(int(token.id), **fields)
            token = google_sheet_token_repository.get_entity(int(token.id))

        google_sheet_token_repository.commit()

        logger.info("Imported Google Sheet token successfully: %s", token.name)
        return self._serialize_token(token), is_new

    def update_token(self, token_id: int, **payload):
        token = google_sheet_token_repository.get_entity(int(token_id))
        if not token:
            raise NotFoundError("所选 Token 不存在")

        fields = {}
        name = payload.get("name")
        max_usage_count = payload.get("max_usage_count")
        is_active = payload.get("is_active")
        token_context = payload.get("token_context")
        task_type = payload.get("task_type")

        if name is not None:
            fields["name"] = str(name).strip() or token.name
        if max_usage_count is not None:
            fields["max_usage_count"] = max(0, int(max_usage_count))
        if is_active is not None:
            fields["is_active"] = bool(is_active)
        if task_type is not None:
            fields["task_type"] = self._normalize_token_task_type(task_type)
        if (
            token_context is not None
            and str(token_context).strip()
            and not is_masked_token_context(token_context)
        ):
            fields["token_context"] = self._load_token_context(token_context=token_context)

        if fields:
            google_sheet_token_repository.update_fields(int(token_id), **fields)
            token = google_sheet_token_repository.get_entity(int(token_id))

        google_sheet_token_repository.commit()
        return self._serialize_token(token)

    def delete_token(self, token_id: int) -> bool:
        """删除 Token（google-sheet-tokens DELETE 端点）；不存在返回 False。"""
        return google_sheet_token_repository.delete(token_id)

    def get_usage_summary(self):
        # Separate current occupancy from historical usage.（只读，不做对账写库）
        global_max_usage = self._get_global_max_usage()
        current_total = google_sheet_token_repository.sum_field('current_in_use_count')
        total_usage = google_sheet_token_repository.sum_field('task_usage_count')
        active_count = google_sheet_token_repository.count_active()
        available_count = sum(
            1 for token in google_sheet_token_repository.list_active_entities() if _token_is_available(token)
        )
        return {
            "current_total_in_use": int(current_total),
            "current_total_usage": int(total_usage),
            "global_max_usage": int(global_max_usage),
            "active_token_count": int(active_count),
            "available_token_count": int(available_count),
        }

    def resolve_task_token(self, config: Dict[str, Any]):
        """任务执行期解析 Token：优先 token_id；旧配置无 token_id 时取首个可用 Token。"""
        data = config if isinstance(config, dict) else {}
        token_id = data.get("token_id")
        if token_id:
            token = google_sheet_token_repository.get_entity(int(token_id))
            if not token:
                raise ValidationError("任务配置的 Token 不存在")
            return token

        task_type = self._normalize_token_task_type(data.get("token_task_type"))
        default_token_id = self._get_default_token_id()
        if default_token_id:
            token = google_sheet_token_repository.get_entity(int(default_token_id))
            actual_task_type = (
                (getattr(token, "task_type", None) or GoogleSheetTokenTaskType.GOOGLE_SHEET.value)
                if token
                else None
            )
            if token and bool(getattr(token, "is_active", False)) and (
                not task_type or actual_task_type == task_type
            ):
                return token
            logger.warning("默认 Token 不可用（id=%s），回退首个可用 Token", default_token_id)

        tokens = [
            token
            for token in google_sheet_token_repository.list_entities_ordered(task_type)
            if bool(getattr(token, "is_active", False))
        ]
        if not tokens:
            raise ValidationError("任务未配置 Token，且没有可用 Token，请先导入并启用 Token")
        return tokens[0]

    def prepare_task_config(self, config: Dict[str, Any]):
        if not isinstance(config, dict):
            return config

        resolved = dict(config)
        resolved.pop("token_json", None)

        # 配置经规范化会把缺失键补成 None；None 视为默认 file 形态（API 调用方
        # 可能不显式携带 token_type）。
        token_type = resolved.get("token_type") or "file"
        if token_type != "file":
            return resolved

        self._assert_global_usage_available()
        resolved.pop("token_file", None)

        token_selection = config.get("token_id")
        if token_selection in (None, "", 0, "0"):
            # 创建期不强制选 Token；执行期 resolve_task_token 会取首个可用 Token。
            return resolved

        token_task_type = self._normalize_token_task_type(config.get("token_task_type"))
        token = self._pick_token(token_selection, task_type=token_task_type)
        resolved["token_id"] = token.id
        resolved["token_name"] = token.name
        if token_selection == RANDOM_TOKEN_VALUE:
            resolved["token_selection_mode"] = RANDOM_TOKEN_VALUE
        return resolved

    def validate_task_start(self, config: Dict[str, Any]):
        if not isinstance(config, dict):
            return

        token_type = config.get("token_type") or "file"
        if token_type != "file":
            return

        snapshot = self._build_live_usage_snapshot()
        self._assert_global_usage_available(current_total=snapshot["current_total"])

        token_id = config.get("token_id")
        if not token_id:
            return

        token = google_sheet_token_repository.get_entity(int(token_id))
        if not token:
            raise NotFoundError("所选 Token 不存在")
        expected_task_type = self._normalize_token_task_type(config.get("token_task_type"))
        actual_task_type = token.task_type or GoogleSheetTokenTaskType.GOOGLE_SHEET.value
        if expected_task_type and actual_task_type != expected_task_type:
            raise ValidationError(f"Token [{token.name}] 不适用于当前任务类型")
        current_in_use = int(snapshot["token_usage"].get(int(token.id), 0))
        self._assert_token_usage_available(token, current_in_use)

    def increment_usage(self, token_id: Optional[int]):
        if not token_id:
            return None

        snapshot = self._build_live_usage_snapshot()
        self._assert_global_usage_available(current_total=snapshot["current_total"])

        token = google_sheet_token_repository.get_entity(int(token_id))
        if not token:
            raise NotFoundError("所选 Token 不存在")
        current_in_use = int(snapshot["token_usage"].get(int(token.id), 0))
        self._assert_token_usage_available(token, current_in_use)

        google_sheet_token_repository.update_fields(
            int(token_id),
            task_usage_count=int(token.task_usage_count or 0) + 1,
            current_in_use_count=current_in_use + 1,
            last_used_at=datetime.now(),
        )
        return google_sheet_token_repository.get_entity(int(token_id))

    def release_usage(self, token_id: Optional[int]):
        if not token_id:
            return None

        token = google_sheet_token_repository.get_entity(int(token_id))
        if not token:
            return None

        google_sheet_token_repository.update_fields(
            int(token_id),
            current_in_use_count=max(0, int(token.current_in_use_count or 0) - 1),
            last_used_at=datetime.now(),
        )
        return google_sheet_token_repository.get_entity(int(token_id))

    def _load_token_context(self, token_context: Optional[str] = None):
        raw_context = (token_context or "").strip()

        if not raw_context:
            raise ValidationError("token内容不能为空")
        if is_masked_token_context(raw_context):
            raise ValidationError("Token 内容为脱敏展示，请粘贴完整 Token JSON")

        try:
            parsed = loads(raw_context)
        except JSONDecodeError as exc:
            raise ValidationError(f"token内容不是有效JSON: {exc}") from exc

        return dumps(parsed, ensure_ascii=False, indent=2)

    def _pick_token(self, token_selection: Any, task_type: Optional[str] = None):
        snapshot = self._build_live_usage_snapshot()
        normalized_task_type = self._normalize_token_task_type(task_type)
        if str(token_selection) == RANDOM_TOKEN_VALUE:
            return self._pick_random_available_token(snapshot=snapshot, task_type=normalized_task_type)

        token = google_sheet_token_repository.get_entity(int(token_selection))
        if not token:
            raise NotFoundError("所选 Token 不存在")
        actual_task_type = token.task_type or GoogleSheetTokenTaskType.GOOGLE_SHEET.value
        if normalized_task_type and actual_task_type != normalized_task_type:
            raise ValidationError(f"Token [{token.name}] 不属于 {normalized_task_type} 分组")
        current_in_use = int(snapshot["token_usage"].get(int(token.id), 0))
        self._assert_token_usage_available(token, current_in_use)
        return token

    def _pick_random_available_token(self, snapshot: Optional[Dict[str, Any]] = None, task_type: Optional[str] = None):
        snapshot = snapshot or self._build_live_usage_snapshot()
        token_usage = snapshot["token_usage"]
        normalized_task_type = self._normalize_token_task_type(task_type)
        tokens = google_sheet_token_repository.list_active_entities(task_type=normalized_task_type)
        # 单 Token 排序键对齐原 ORM order_by（HTTP 后端返回 list，本地排序）。
        tokens = sorted(
            tokens,
            key=lambda token: (
                int(token.current_in_use_count or 0),
                int(token.task_usage_count or 0),
                int(token.id or 0),
            ),
        )
        available = []
        for token in tokens:
            current_in_use = int(token_usage.get(int(token.id), 0))
            max_usage = int(token.max_usage_count or 0)
            if max_usage <= 0 or current_in_use < max_usage:
                available.append((token, current_in_use))
        if not available:
            raise ValidationError(
                "所有 Token 都已达到上限，请先调整 Token 或系统上限配置"
            )

        min_usage = min(current_in_use for _, current_in_use in available)
        candidates = [token for token, current_in_use in available if current_in_use == min_usage]
        return random.choice(candidates)

    def _assert_global_usage_available(self, current_total: Optional[int] = None):
        max_usage = self._get_global_max_usage()
        if max_usage <= 0:
            return

        if current_total is None:
            current_total = google_sheet_token_repository.sum_field('current_in_use_count')
        if int(current_total) >= max_usage:
            raise ValidationError(
                f"所有 Token 当前占用次数已达到系统上限({max_usage})，停止生成任务"
            )

    def _get_default_token_id(self):
        value = get_config_manager().get_config("default_token_id", "")
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _get_global_max_usage(self):
        value = get_config_manager().get_config("google_sheet_token_global_max_usage", 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _build_default_name(token_id: Optional[int] = None):
        return f"Google Token #{int(token_id)}" if token_id else "Google Token"

google_sheet_token_service = GoogleSheetTokenService()


def get_google_sheet_token_service():
    return google_sheet_token_service
