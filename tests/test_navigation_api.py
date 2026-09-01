import os
from unittest.mock import patch
import unittest

from flask import Flask

from app.repositories.sdk_client import SdkDataAccessError
from app.routes.meta_api import meta_api_bp


class NavigationApiTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(meta_api_bp, url_prefix="/api")

    def test_remote_menu_failure_returns_503(self):
        with self.app.test_client() as client, patch.dict(os.environ, {"AUTH_ENABLED": "false"}), patch(
            "app.routes.meta_api._get_remote_menu",
            side_effect=SdkDataAccessError("offline"),
        ):
            response = client.get("/api/navigation/menu")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["code"], 503)
