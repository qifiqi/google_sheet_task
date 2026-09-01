from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import unittest

import jwt
from flask import Flask, g

from app.services.remote_identity_service import RemoteUser
from app.utils.auth import authenticate_current_request, is_retired_local_identity_path


class RemoteGatewayAuthTests(unittest.TestCase):
    secret = "test-gateway-secret-with-sufficient-length"

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["REMOTE_MODEL_CODES_CLAIM"] = "model_codes"

    def _token(self, **payload):
        default = {
            "userid": 28,
            "username": "gateway-user",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        default.update(payload)
        return jwt.encode(default, self.secret, algorithm="HS256")

    def _authenticate(self, token, remote_user=RemoteUser(id=28, username="gateway-user")):
        with self.app.test_request_context("/api/auth/me", headers={"Authorization": f"Bearer {token}"}):
            with patch("app.utils.auth._get_secret", return_value=self.secret), patch(
                "app.utils.auth.is_auth_enabled", return_value=True,
            ), patch(
                "app.services.remote_identity_service.RemoteIdentityService.get_user",
                return_value=remote_user,
            ):
                result = authenticate_current_request()
            return result, getattr(g, "current_user", None), getattr(g, "current_model_codes", None)

    def test_accepts_main_web_userid_and_model_codes(self):
        result, user, model_codes = self._authenticate(
            self._token(model_codes=["TaskManage", "SheetManage"])
        )
        self.assertIsNone(result)
        self.assertEqual(user.id, 28)
        self.assertEqual(model_codes, {"TaskManage", "SheetManage"})

    def test_expired_and_forged_token_return_401(self):
        expired = self._token(exp=datetime.now(timezone.utc) - timedelta(seconds=1))
        result, _, _ = self._authenticate(expired)
        self.assertEqual(result[1], 401)

        forged = jwt.encode(
            {"userid": 28, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            "other-secret-with-sufficient-length",
            algorithm="HS256",
        )
        result, _, _ = self._authenticate(forged)
        self.assertEqual(result[1], 401)

    def test_missing_or_disabled_remote_user_returns_401(self):
        result, _, _ = self._authenticate(self._token(), remote_user=None)
        self.assertEqual(result[1], 401)

        with self.app.test_request_context("/api/auth/me", headers={"Authorization": f"Bearer {self._token()}"}):
            with patch("app.utils.auth._get_secret", return_value=self.secret), patch(
                "app.utils.auth.is_auth_enabled", return_value=True,
            ), patch(
                "app.services.remote_identity_service.SysUserRepository.get_by_id",
                return_value={"userid": 28, "username": "gateway-user", "is_frozen": 1},
            ):
                result = authenticate_current_request()
        self.assertEqual(result[1], 401)

    def test_retired_identity_paths_are_all_recognized(self):
        for path in (
            "/admin/users", "/admin/roles", "/admin/navigation",
            "/api/admin/users/1", "/api/admin/roles/1",
            "/api/admin/permissions", "/api/auth/password",
            "/api/navigation-menu-items/1",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_retired_local_identity_path(path))
