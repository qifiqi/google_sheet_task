from __future__ import annotations

import json
import mimetypes
import os
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from openpyxl import Workbook


BASE_DIR = Path(__file__).resolve().parent
TOKEN_PATH = BASE_DIR / "token.json"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"

# This demo implements its own Drive folder browser, so it needs folder listing
# permission in addition to upload permission. For production, narrow this if
# you replace the browser with Google Picker or constrain allowed folders.
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GoogleDriveRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def create_app() -> Flask:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-google-drive-upload-demo")

    @app.get("/")
    def index():
        auth_state = get_auth_state()
        return render_template(
            "index.html",
            auth_state=auth_state,
            picker_config=get_picker_config(),
        )

    @app.post("/api/global-preview/upload")
    def upload_global_preview():
        data = request.get_json(silent=True) or {}
        folder_id = data.get("folder_id") or "root"
        file_name = normalize_xlsx_filename(data.get("file_name") or "")
        preview_type = data.get("preview_type") or "single"

        if not file_name:
            return jsonify({"error": "文件名不能为空"}), 400

        workbook_bytes = build_demo_global_preview_workbook(preview_type)

        credentials = load_credentials()
        if credentials is None:
            return jsonify({"error": "请先完成 Google 授权"}), 401

        try:
            file_result = google_drive_upload_file(
                credentials=credentials,
                folder_id=folder_id,
                file_name=file_name,
                content=workbook_bytes,
                mime_type=XLSX_MIME_TYPE,
            )
            return jsonify({"file": file_result})
        except GoogleDriveRequestError as err:
            return jsonify({"error": str(err)}), err.status_code
        except requests.RequestException as err:
            return jsonify({"error": f"上传 Google Drive 失败: {err}"}), 502

    @app.get("/api/drive/folder-path")
    def get_folder_path():
        folder_id = request.args.get("folder_id", type=str)
        if not folder_id:
            return jsonify({"error": "folder_id 不能为空"}), 400

        credentials = load_credentials()
        if credentials is None:
            return jsonify({"error": "请先完成 Google 授权"}), 401

        try:
            path = resolve_drive_folder_path(credentials, folder_id)
            return jsonify(path)
        except ValueError as err:
            return jsonify({"error": str(err)}), 400
        except requests.RequestException as err:
            return jsonify({"error": f"解析 Google Drive 路径失败: {err}"}), 502

    @app.get("/auth/google/token")
    def google_auth_token():
        credentials = load_credentials()
        if credentials is None:
            return jsonify({"error": "请先完成 Google 授权"}), 401
        return jsonify(
            {
                "access_token": credentials.token,
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            }
        )

    @app.get("/auth/google/start")
    def google_auth_start():
        if not CLIENT_SECRET_PATH.exists():
            return (
                "缺少 client_secret.json。请把 Google OAuth 客户端密钥保存到 demo 目录后重试。",
                400,
            )

        flow = Flow.from_client_secrets_file(
            str(CLIENT_SECRET_PATH),
            scopes=DRIVE_SCOPES,
            redirect_uri=url_for("google_auth_callback", _external=True),
        )
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        session["oauth_state"] = state
        return redirect(authorization_url)

    @app.get("/auth/google/callback")
    def google_auth_callback():
        state = session.get("oauth_state")
        flow = Flow.from_client_secrets_file(
            str(CLIENT_SECRET_PATH),
            scopes=DRIVE_SCOPES,
            state=state,
            redirect_uri=url_for("google_auth_callback", _external=True),
        )
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
        return redirect(url_for("index"))

    @app.post("/auth/google/logout")
    def google_auth_logout():
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()
        return jsonify({"ok": True})

    return app


def get_auth_state() -> dict[str, Any]:
    credentials = load_credentials()
    return {
        "mode": "google",
        "authorized": credentials is not None,
        "label": "Google Drive 已授权" if credentials else "等待 Google 授权",
    }


def get_picker_config() -> dict[str, Any]:
    api_key = os.getenv("GOOGLE_PICKER_API_KEY", "AIzaSyA_vbR-5YjR94h3UJ4Z0fbBdJyflMixyx8").strip()
    app_id = os.getenv("GOOGLE_PICKER_APP_ID", "automated-alloy-497609-g1").strip()
    return {
        "api_key": api_key,
        "app_id": app_id,
        "ready": bool(api_key and app_id),
    }


def load_credentials() -> Credentials | None:
    if not TOKEN_PATH.exists():
        return None

    credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), DRIVE_SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    if not credentials.valid:
        return None
    return credentials


def normalize_xlsx_filename(file_name: str) -> str:
    clean_name = file_name.strip().replace("\\", "_").replace("/", "_")
    if not clean_name:
        return ""
    if not clean_name.lower().endswith(".xlsx"):
        clean_name += ".xlsx"
    return clean_name


def build_demo_global_preview_workbook(preview_type: str) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "摘要"
    summary.append(["预览类型", "生成时间", "说明"])
    summary.append(
        [
            "多产品全局预览" if preview_type == "multi" else "单产品全局预览",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "这是 Google Drive 上传 demo 生成的示例 Excel。",
        ]
    )

    detail = workbook.create_sheet("全局预览")
    detail.append(["参数方案", "产品", "指数值", "模型结果", "备注"])

    rows = (
        [
            ["方案 A", "产品 1 + 产品 2", "18.50%", "24.20%", "组合比例 60% / 40%"],
            ["方案 B", "产品 1 + 产品 2", "12.30%", "19.80%", "组合比例 50% / 50%"],
        ]
        if preview_type == "multi"
        else [
            ["方案 A", "产品 1", "18.50%", "24.20%", "单产品"],
            ["方案 B", "产品 1", "12.30%", "19.80%", "单产品"],
        ]
    )
    for row in rows:
        detail.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def resolve_drive_folder_path(credentials: Credentials, folder_id: str) -> dict[str, Any]:
    session_client = AuthorizedSession(credentials)
    current_id = folder_id
    path_segments: list[str] = []
    seen_ids: set[str] = set()

    while current_id and current_id != "root":
        if current_id in seen_ids:
            raise ValueError("检测到循环父路径")
        seen_ids.add(current_id)

        response = session_client.get(
            f"https://www.googleapis.com/drive/v3/files/{current_id}",
            params={"fields": "id,name,parents,mimeType", "supportsAllDrives": "true"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise GoogleDriveRequestError(
                f"解析 Google Drive 路径失败: {response.status_code} {response.text}",
                status_code=502,
            )
        metadata = response.json()
        path_segments.append(metadata.get("name") or current_id)
        parents = metadata.get("parents") or []
        current_id = parents[0] if parents else None

    path_segments.reverse()
    return {
        "folder_id": folder_id,
        "display_path": "/" + "/".join(path_segments) if path_segments else "/",
        "segments": path_segments,
    }


def google_drive_upload_file(
    credentials: Credentials,
    folder_id: str,
    file_name: str,
    content: bytes,
    mime_type: str,
) -> dict[str, Any]:
    session_client = AuthorizedSession(credentials)
    metadata = {
        "name": file_name,
        "parents": [folder_id],
        "mimeType": mime_type,
    }

    boundary = f"codex_drive_upload_{uuid.uuid4().hex}"
    body = build_multipart_upload_body(boundary, metadata, content, mime_type)
    response = session_client.post(
        "https://www.googleapis.com/upload/drive/v3/files",
        params={
            "uploadType": "multipart",
            "fields": "id,name,mimeType,size,webViewLink",
            "supportsAllDrives": "true",
        },
        data=body,
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        timeout=60,
    )
    if response.status_code >= 400:
        raise GoogleDriveRequestError(
            f"上传 Google Drive 失败: {response.status_code} {response.text}",
            status_code=502,
        )
    return response.json()


def build_multipart_upload_body(
    boundary: str,
    metadata: dict[str, Any],
    content: bytes,
    mime_type: str,
) -> bytes:
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
        b"\r\n",
        f"--{boundary}\r\n".encode("utf-8"),
        f"Content-Type: {mime_type or mimetypes.guess_type(metadata['name'])[0] or 'application/octet-stream'}\r\n\r\n".encode(
            "utf-8"
        ),
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts)


if __name__ == "__main__":
    create_app().run(debug=True, port=5010)
