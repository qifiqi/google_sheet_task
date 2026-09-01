import unittest

from flask import Flask

from app.services.model_access_service import require_model_access, set_current_model_codes


class ModelAccessServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_requires_user_scoped_model_code(self):
        @require_model_access("TaskManage")
        def protected():
            return "ok"

        with self.app.test_request_context("/"):
            set_current_model_codes({"TaskManage"})
            self.assertEqual(protected(), "ok")

        with self.app.test_request_context("/"):
            response, status = protected()
            self.assertEqual(status, 503)
            self.assertEqual(response.get_json()["code"], 503)

        with self.app.test_request_context("/"):
            set_current_model_codes({"OtherManage"})
            response, status = protected()
            self.assertEqual(status, 403)
            self.assertEqual(response.get_json()["code"], 403)

