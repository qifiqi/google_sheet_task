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
            GoogleSheetToken.current_in_use_count.asc(),
            GoogleSheetToken.task_usage_count.asc(),
            GoogleSheetToken.name.asc(),
        ).all()
        return [token.to_dict() for token in tokens]

    def get_token(self, token_id: int, include_context: bool = False):
        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("?? Token ???")
        return token.to_dict(include_context=include_context)

    def import_token(
        self,
        token_context: Optional[str] = None,
        name: Optional[str] = None,
        max_usage_count: Optional[int] = None,
        token_file: Optional[str] = None,
    ):
        normalized_context = self._load_token_context(token_context=token_context, token_file=token_file)
        token = GoogleSheetToken.query.filter_by(token_context=normalized_context).first()
        is_new = token is None

        if token is None:
            token = GoogleSheetToken(
                name=(name or "").strip() or self._build_default_name(),
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
        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("?? Token ???")

        name = payload.get("name")
        max_usage_count = payload.get("max_usage_count")
        is_active = payload.get("is_active")
        token_context = payload.get("token_context")

        if name is not None:
            token.name = str(name).strip() or token.name
        if max_usage_count is not None:
            token.max_usage_count = max(0, int(max_usage_count))
        if is_active is not None:
            token.is_active = bool(is_active)
        if token_context is not None:
            token.token_context = self._load_token_context(token_context=token_context)
        if not token.token_file:
            db.session.flush()
            token.token_file = self._build_runtime_token_file(token.id)

        db.session.flush()
        self.ensure_token_file(token)
        db.session.commit()
        return token.to_dict()

    def get_usage_summary(self):
        # Separate current occupancy from historical usage.
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
        if not isinstance(config, dict):
            return config

        token_type = config.get("token_type", "file")
        if token_type != "file":
            return config

        self._assert_global_usage_available()

        token_selection = config.get("token_id")
        if token_selection in (None, "", 0, "0"):
            return config

        token = self._pick_token(token_selection)
        token_file = self.ensure_token_file(token)

        resolved = dict(config)
        resolved["token_id"] = token.id
        resolved["token_file"] = token_file
        resolved["token_name"] = token.name
        if token_selection == RANDOM_TOKEN_VALUE:
            resolved["token_selection_mode"] = RANDOM_TOKEN_VALUE
        return resolved

    def validate_task_start(self, config: Dict[str, Any]):
        if not isinstance(config, dict):
            return

        token_type = config.get("token_type", "file")
        if token_type != "file":
            return

        self._assert_global_usage_available()

        token_id = config.get("token_id")
        if not token_id:
            return

        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("?? Token ???")

        if not token.is_available():
            raise ValueError(
                f"Token [{token.name}] \u5df2\u8fbe\u5230\u6700\u5927\u5360\u7528\u6b21\u6570\uff0c\u8bf7\u66f4\u6362 Token"
            )

    def increment_usage(self, token_id: Optional[int]):
        if not token_id:
            return None

        self._assert_global_usage_available()

        token = GoogleSheetToken.query.get(int(token_id))
        if not token:
            raise ValueError("?? Token ???")

        if not token.is_available():
            raise ValueError(
                f"Token [{token.name}] \u5df2\u8fbe\u5230\u6700\u5927\u5360\u7528\u6b21\u6570\uff0c\u8bf7\u66f4\u6362 Token"
            )

        token.task_usage_count = int(token.task_usage_count or 0) + 1
        token.current_in_use_count = int(token.current_in_use_count or 0) + 1
        token.last_used_at = datetime.now()
        db.session.commit()
        return token

    def release_usage(self, token_id: Optional[int]):
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
        raw_context = (token_context or "").strip()
        if not raw_context and token_file:
            token_path = Path(token_file)
            if not token_path.is_absolute():
                token_path = Path.cwd() / token_path
            if not token_path.exists():
                raise ValueError(f"token?????: {token_file}")
            raw_context = token_path.read_text(encoding="utf-8")

        if not raw_context:
            raise ValueError("token??????")

        try:
            parsed = json.loads(raw_context)
        except json.JSONDecodeError as exc:
            raise ValueError(f"token??????JSON: {exc}") from exc

        return json.dumps(parsed, ensure_ascii=False, indent=2)

    def ensure_token_file(self, token: GoogleSheetToken):
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

    def _pick_token(self, token_selection: Any):
        if str(token_selection) == RANDOM_TOKEN_VALUE:
            return self._pick_random_available_token()

        token = GoogleSheetToken.query.get(int(token_selection))
        if not token:
            raise ValueError("?? Token ???")
        if not token.is_available():
            raise ValueError(
                f"Token [{token.name}] \u5df2\u8fbe\u5230\u6700\u5927\u5360\u7528\u6b21\u6570\uff0c\u8bf7\u66f4\u6362 Token"
            )
        return token

    def _pick_random_available_token(self):
        tokens = GoogleSheetToken.query.filter_by(is_active=True).order_by(
            GoogleSheetToken.current_in_use_count.asc(),
            GoogleSheetToken.task_usage_count.asc(),
            GoogleSheetToken.id.asc(),
        ).all()
        available = [token for token in tokens if token.is_available()]
        if not available:
            raise ValueError(
                "?? Token ??????????? Token ???????"
            )

        min_usage = min(int(token.current_in_use_count or 0) for token in available)
        candidates = [token for token in available if int(token.current_in_use_count or 0) == min_usage]
        return random.choice(candidates)

    def _assert_global_usage_available(self):
        max_usage = self._get_global_max_usage()
        if max_usage <= 0:
            return

        current_total = db.session.query(
            db.func.coalesce(db.func.sum(GoogleSheetToken.current_in_use_count), 0)
        ).scalar() or 0
        if int(current_total) >= max_usage:
            raise ValueError(
                f"?? Token ?????????????({max_usage})???????"
            )

    def _get_global_max_usage(self):
        value = get_config_manager().get_config("google_sheet_token_global_max_usage", 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _build_default_name(token_id: Optional[int] = None):
        return f"Google Token #{int(token_id)}" if token_id else "Google Token"

    @staticmethod
    def _build_runtime_token_file(token_id: int):
        return f"data/google_sheet_tokens/token_{int(token_id)}.json"


google_sheet_token_service = GoogleSheetTokenService()


def get_google_sheet_token_service():
    return google_sheet_token_service
