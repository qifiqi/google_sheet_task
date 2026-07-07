"""Configuration for the DingTalk stream microservice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DingStreamSettings:
    client_id: str
    client_secret: str
    project_root: Path

    @classmethod
    def from_env(cls) -> "DingStreamSettings":
        load_dotenv(PROJECT_ROOT / ".env")
        app_env = os.getenv("APP_ENV", "development").strip().lower() or "development"
        load_dotenv(PROJECT_ROOT / f".env.{app_env}", override=True)

        client_id = os.getenv("DING_STREAM_CLIENT_ID", "").strip()
        client_secret = os.getenv("DING_STREAM_CLIENT_SECRET", "").strip()

        if not client_id or not client_secret:
            raise ValueError(
                "请在项目根目录 .env 中配置 DING_STREAM_CLIENT_ID 和 "
                "DING_STREAM_CLIENT_SECRET"
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            project_root=PROJECT_ROOT,
        )
