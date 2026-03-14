import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.extensions import db
from app.models import GoogleSheetToken
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)

RANDOM_TOKEN_VALUE = "__random__"


class GoogleSheetTokenService:
    def list_tokens(self):
        tokens = GoogleSheetToken.query.order_by(
            GoogleSheetToken.is_active.desc(),
            GoogleSheetToken.task_usage_count.asc(),
            GoogleSheetToken.name.asc()
        ).all()
        return [token.to_dict() for token in tokens]

    def get_token(self, token_id: int, include_context: bool = False):
        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("所选Token不存在")
        return token.to_dict(include_context=include_context)

    def import_token(self, token_file: str, name: Optional[str] = None, max_usage_count: Optional[int] = None):
        if not token_file:
            raise ValueError("token文件路径不能为空")

        token_path = Path(token_file)
        if not token_path.is_absolute():
            token_path = Path.cwd() / token_path

        if not token_path.exists():
            raise ValueError(f"token文件不存在: {token_file}")

        try:
            token_context = token_path.read_text(encoding='utf-8')
            json.loads(token_context)
        except json.JSONDecodeError as exc:
            raise ValueError(f"token文件不是有效JSON: {exc}") from exc

        stored_path = self._normalize_stored_path(token_file)
        token = GoogleSheetToken.query.filter_by(token_file=stored_path).first()
        is_new = token is None

        if token is None:
            token = GoogleSheetToken(
                name=name or token_path.stem,
                token_file=stored_path,
                token_context=token_context,
                max_usage_count=max_usage_count if max_usage_count is not None else 0,
                is_active=True,
            )
            db.session.add(token)
        else:
            token.name = name or token.name or token_path.stem
            token.token_context = token_context
            token.is_active = True
            if max_usage_count is not None:
                token.max_usage_count = max_usage_count

        db.session.flush()
        self.ensure_token_file(token)
        db.session.commit()

        logger.info("导入Google Sheet Token成功: %s", token.token_file)
        return token.to_dict(), is_new

    def update_token(self, token_id: int, **payload):
        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("所选Token不存在")

        name = payload.get('name')
        max_usage_count = payload.get('max_usage_count')
        is_active = payload.get('is_active')
        token_context = payload.get('token_context')

        if name is not None:
            token.name = str(name).strip() or token.name
        if max_usage_count is not None:
            token.max_usage_count = max(0, int(max_usage_count))
        if is_active is not None:
            token.is_active = bool(is_active)
        if token_context is not None:
            parsed = json.loads(token_context)
            token.token_context = json.dumps(parsed, ensure_ascii=False, indent=2)

        db.session.flush()
        self.ensure_token_file(token)
        db.session.commit()
        return token.to_dict()

    def get_usage_summary(self):
        global_max_usage = self._get_global_max_usage()
        current_total = db.session.query(
            db.func.coalesce(db.func.sum(GoogleSheetToken.task_usage_count), 0)
        ).scalar() or 0
        active_count = GoogleSheetToken.query.filter_by(is_active=True).count()
        available_count = sum(
            1 for token in GoogleSheetToken.query.filter_by(is_active=True).all() if token.is_available()
        )
        return {
            'current_total_usage': int(current_total),
            'global_max_usage': int(global_max_usage),
            'active_token_count': int(active_count),
            'available_token_count': int(available_count),
        }

    def prepare_task_config(self, config: Dict[str, Any]):
        if not isinstance(config, dict):
            return config

        token_type = config.get('token_type', 'file')
        if token_type != 'file':
            return config

        self._assert_global_usage_available()

        token_selection = config.get('token_id')
        if token_selection in (None, '', 0, '0'):
            return config

        token = self._pick_token(token_selection)
        token_file = self.ensure_token_file(token)

        resolved = dict(config)
        resolved['token_id'] = token.id
        resolved['token_file'] = token_file
        resolved['token_name'] = token.name
        if token_selection == RANDOM_TOKEN_VALUE:
            resolved['token_selection_mode'] = RANDOM_TOKEN_VALUE
        return resolved

    def validate_task_start(self, config: Dict[str, Any]):
        if not isinstance(config, dict):
            return

        token_type = config.get('token_type', 'file')
        if token_type != 'file':
            return

        self._assert_global_usage_available()

        token_id = config.get('token_id')
        if not token_id:
            return

        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("所选Token不存在")

        if not token.is_available():
            raise ValueError(f"Token [{token.name}] 已达到最大使用次数，请更换Token")

    def increment_usage(self, token_id: Optional[int]):
        if not token_id:
            return None

        self._assert_global_usage_available()

        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("所选Token不存在")

        if not token.is_available():
            raise ValueError(f"Token [{token.name}] 已达到最大使用次数，请更换Token")

        token.task_usage_count = int(token.task_usage_count or 0) + 1
        token.last_used_at = datetime.now()
        db.session.commit()
        return token

    def ensure_token_file(self, token: GoogleSheetToken):
        original_path = Path(token.token_file)
        if original_path.is_absolute():
            target_path = original_path
        else:
            target_path = Path.cwd() / original_path

        if not target_path.parent.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)

        if not target_path.exists() or target_path.read_text(encoding='utf-8') != token.token_context:
            target_path.write_text(token.token_context, encoding='utf-8')

        return str(target_path.relative_to(Path.cwd())) if str(target_path).startswith(str(Path.cwd())) else str(target_path)

    def _pick_token(self, token_selection: Any):
        if str(token_selection) == RANDOM_TOKEN_VALUE:
            return self._pick_random_available_token()

        token = GoogleSheetToken.query.get(int(token_selection))
        if not token:
            raise ValueError("所选Token不存在")
        if not token.is_available():
            raise ValueError(f"Token [{token.name}] 已达到最大使用次数，请更换Token")
        return token

    def _pick_random_available_token(self):
        tokens = GoogleSheetToken.query.filter_by(is_active=True).order_by(
            GoogleSheetToken.task_usage_count.asc(),
            GoogleSheetToken.id.asc()
        ).all()
        available = [token for token in tokens if token.is_available()]
        if not available:
            raise ValueError("所有Token都已达到上限，请先调整Token或系统上限配置")

        min_usage = min(int(token.task_usage_count or 0) for token in available)
        candidates = [token for token in available if int(token.task_usage_count or 0) == min_usage]
        return random.choice(candidates)

    def _assert_global_usage_available(self):
        max_usage = self._get_global_max_usage()
        if max_usage <= 0:
            return

        current_total = db.session.query(db.func.coalesce(db.func.sum(GoogleSheetToken.task_usage_count), 0)).scalar() or 0
        if int(current_total) >= max_usage:
            raise ValueError(f"所有Token累计使用次数已达到系统上限({max_usage})，停止生成任务")

    def _get_global_max_usage(self):
        value = get_config_manager().get_config('google_sheet_token_global_max_usage', 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_stored_path(token_file: str):
        file_path = Path(token_file)
        if file_path.is_absolute():
            try:
                return str(file_path.relative_to(Path.cwd()))
            except ValueError:
                return str(file_path)
        return str(file_path).replace('\\', '/')


google_sheet_token_service = GoogleSheetTokenService()


def get_google_sheet_token_service():
    return google_sheet_token_service
