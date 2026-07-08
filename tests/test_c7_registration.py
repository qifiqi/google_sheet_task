from app.config import PERMISSIONS
from app.models import TaskType
from app.navigation import build_nav_permission_map, normalize_nav_path
from app.services.model_summary_service import SUPPORTED_TASK_TYPES
from app.services.task import TaskManager
from app.services.task.query import _task_type_filter_values
from app.utils.task_authorization import authorize_task_type_action, normalize_task_type


class FakeUser:
    def __init__(self, permissions):
        self._permissions = set(permissions)

    def get_permissions(self):
        return self._permissions


def test_c_series_task_types_are_registered_for_filters():
    assert TaskType.normalize("google_sheet_c4") == "google_sheet_C4"
    assert TaskType.normalize("google_sheet_c5") == "google_sheet_C5"
    assert TaskType.normalize("google_sheet_c7") == "google_sheet_C7"

    choices = {item["value"]: item["label"] for item in TaskType.choices()}
    assert choices["google_sheet_C4"] == "Google Sheet C4"
    assert choices["google_sheet_C5"] == "Google Sheet C5"
    assert choices["google_sheet_C7"] == "Google Sheet C7"
    assert "google_sheet_C7" in SUPPORTED_TASK_TYPES


def test_c7_navigation_and_permissions_are_registered():
    permissions = {code for _group, code, _name, _route_path in PERMISSIONS}
    assert "google_sheet:c7" in permissions
    assert "page:google_sheet:c7" in permissions

    permission_map = build_nav_permission_map()
    assert normalize_nav_path("/task/list?version=c7") == "/google-sheet/?version=c7"
    assert permission_map["/google-sheet/?version=c7"] == "page:google_sheet:c7"
    assert permission_map["/task/list?version=c7"] == "page:google_sheet:c7"


def test_c7_requires_scoped_google_sheet_permission():
    assert normalize_task_type("google_sheet_C7") == "google_sheet_c7"

    missing_scope = authorize_task_type_action(
        FakeUser({"task:create"}),
        "create",
        "google_sheet_C7",
    )
    assert not missing_scope["allowed"]
    assert "google_sheet:c7" in missing_scope["missing_permissions"]

    with_scope = authorize_task_type_action(
        FakeUser({"task:create", "google_sheet:c7"}),
        "create",
        "google_sheet_C7",
    )
    assert with_scope["allowed"]


def test_c_series_task_config_is_saved_with_uppercase_suffix():
    manager = TaskManager()

    config = manager._normalize_task_config_for_type(
        "google_sheet_c7",
        {"task_type": "google_sheet_c7", "spreadsheet_id": "legacy", "sheet_name": "legacy"},
    )

    assert config["task_type"] == "google_sheet_C7"
    assert config["token_task_type"] == "google_sheet"
    assert "spreadsheet_id" not in config
    assert "sheet_name" not in config


def test_c_series_filters_accept_uppercase_and_legacy_lowercase():
    assert _task_type_filter_values("google_sheet_c7") == [
        "google_sheet_C7",
        "google_sheet_c7",
    ]
    assert _task_type_filter_values("google_sheet_C7") == [
        "google_sheet_C7",
        "google_sheet_c7",
    ]
