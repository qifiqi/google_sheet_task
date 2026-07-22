from app.models import TaskType
from app.routes.template_api import _normalize_template_config


def test_template_config_defaults_to_google_sheet_c3_when_type_is_missing():
    config = _normalize_template_config({"stock_codes": ["SOXX"]})

    assert config["task_type"] == TaskType.GOOGLE_SHEET.value


def test_template_config_normalizes_known_task_type_aliases():
    config = _normalize_template_config({"task_type": "google_sheet_C31"})

    assert config["task_type"] == TaskType.GOOGLE_SHEET.value
