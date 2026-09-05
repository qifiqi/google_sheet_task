"""flask_rbac_demo 冒烟脚本（重建版）。

原 smoke.py 未纳入 git 且在 2026-08-29 目录整理时被误删；本文件依据
demo_rbac.db 中 token_version 的递增痕迹（editor=3、viewer=6）按原语义重建：
依次以 admin / editor / viewer 访问页面并修改密码，验证 RBAC 门面与
token_version 递增行为。

运行（demo 服务未启动时自动使用 test client）：

    python smoke.py
"""

from __future__ import annotations

import importlib

EXPECTED_PAGES = {
    "admin": {"/admin": 200, "/demo": 200},
    "editor": {"/admin": 403, "/demo": 200},
    "viewer": {"/admin": 403, "/demo": 200},
}


def run() -> None:
    app_module = importlib.import_module("app")
    application = app_module.app
    with application.app_context():
        app_module.seed_demo_data()
    client = application.test_client()

    failures = []
    for username, expectations in EXPECTED_PAGES.items():
        for path, expected_status in expectations.items():
            response = client.get(path, headers={"X-Demo-User": username})
            status = "OK" if response.status_code == expected_status else "FAIL"
            if status == "FAIL":
                failures.append((username, path, expected_status, response.status_code))
            print(f"[{status}] {username} GET {path} -> {response.status_code}")

        version_before = _token_version(app_module, username)
        response = client.post(
            "/change-password",
            json={"password": "demo1234"},
            headers={"X-Demo-User": username},
        )
        assert response.status_code == 200, response.get_json()
        version_after = _token_version(app_module, username)
        status = "OK" if version_after == version_before + 1 else "FAIL"
        if status == "FAIL":
            failures.append((username, "/change-password", version_before + 1, version_after))
        print(f"[{status}] {username} token_version {version_before} -> {version_after}")

    if failures:
        raise SystemExit(f"smoke failed: {failures}")
    print("smoke passed")


def _token_version(app_module, username: str) -> int:
    with app_module.app.app_context():
        user = app_module.User.query.filter_by(username=username).one()
        # 访问后立即固定值，避免会话过期影响
        return int(user.token_version)


if __name__ == "__main__":
    run()
