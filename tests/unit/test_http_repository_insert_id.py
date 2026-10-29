"""HTTP 仓储插入 id 回填 / E12 预检 / create_with_return 补偿。"""

import pytest

from app.remote_api import RemoteApiError
from app.remote_api.capabilities import require_e12, reset_e12_capability
from app.repositories.http_backend.google_sheet_token_repository import (
    GoogleSheetTokenHttpRepository,
)
from app.repositories.http_backend.task_result_repository import (
    TaskResultHttpRepository,
)


class FakeController:
    def __init__(
        self,
        insert=None,
        page=None,
        fail_modify=None,
        fail_list=None,
        return_row=None,
    ):
        self.insert = insert
        self.page = page if page is not None else ([], 0)
        self.fail_modify = fail_modify
        self.fail_list = fail_list
        self.return_row = return_row
        self.calls = []
        self.deleted = []
        self.last_payload = None
        self.with_count = None

    def modify_or_add(self, payload=None, *, with_count=False, timeout=None):
        self.last_payload = dict(payload or {})
        self.calls.append(self.last_payload)
        self.with_count = with_count
        if self.fail_modify is not None:
            raise self.fail_modify
        if with_count:
            return self.insert if self.insert is not None else (None, None)
        return self.return_row

    def get_data_by_page_list(self, payload=None):
        if self.fail_list is not None:
            raise self.fail_list
        return self.page

    def delete(self, payload=None):
        self.deleted.append(dict(payload or {}))
        return {"ret_code": 200}

    def get_info_by_id(self, payload=None):
        return None


class FakeApi:
    def __init__(self, results=None, returns=None, links=None, tokens=None):
        self.param_task_results = results or FakeController()
        self.param_task_results_return = returns or FakeController()
        self.param_task_result_kline_links = links or FakeController()
        self.param_task_kline_sources = FakeController()
        self.param_task_random_series = FakeController()
        self.param_google_sheet_tokens = tokens or FakeController()


@pytest.fixture(autouse=True)
def _reset_e12_cache():
    reset_e12_capability()
    yield
    reset_e12_capability()


def test_save_captures_insert_id_from_ret_count():
    results = FakeController(insert=(None, 123))
    repo = TaskResultHttpRepository(api=FakeApi(results=results))

    saved = repo.save({"task_id": "t1", "step_index": 0, "success": True})

    assert saved["id"] == 123
    assert results.with_count is True


def test_save_update_does_not_use_count():
    results = FakeController()
    repo = TaskResultHttpRepository(api=FakeApi(results=results))

    saved = repo.save({"id": 7, "task_id": "t1", "step_index": 0, "success": True})

    assert saved["id"] == 7
    assert results.with_count is False


def test_create_with_return_links_real_result_id():
    returns = FakeController(insert=(None, 11))
    results = FakeController(insert=(None, 22))
    links = FakeController(return_row={"id": 88})
    api = FakeApi(results=results, returns=returns, links=links)
    repo = TaskResultHttpRepository(api=api)

    saved = repo.create_with_return(
        {"task_id": "t1", "step_index": 0, "success": True},
        {"task_id": "t1", "stock_code": "600000.SH"},
        kline_series_id=5,
    )

    assert saved["id"] == 22
    assert saved["return_series_id"] == 11
    assert links.last_payload["result_id"] == 22
    assert links.last_payload["series_id"] == 5


def test_create_with_return_compensates_first_step_on_link_failure():
    returns = FakeController(insert=(None, 11))
    results = FakeController(insert=(None, 22), page=([{"id": 22}], 1))
    links = FakeController(fail_modify=RuntimeError("link boom"))
    api = FakeApi(results=results, returns=returns, links=links)
    repo = TaskResultHttpRepository(api=api)

    with pytest.raises(RuntimeError):
        repo.create_with_return(
            {"task_id": "t1", "step_index": 0, "success": True},
            {"task_id": "t1", "stock_code": "600000.SH"},
            kline_series_id=5,
        )

    assert results.deleted == [{"task_id": "t1"}]
    assert returns.deleted == [{"task_id": "t1"}]


def test_create_with_return_skips_task_delete_when_prior_rows_exist():
    returns = FakeController(insert=(None, 11))
    results = FakeController(insert=(None, 22), page=([{"id": 5}], 1))
    links = FakeController(fail_modify=RuntimeError("link boom"))
    api = FakeApi(results=results, returns=returns, links=links)
    repo = TaskResultHttpRepository(api=api)

    with pytest.raises(RuntimeError):
        repo.create_with_return(
            {"task_id": "t1", "step_index": 3, "success": True},
            {"task_id": "t1", "stock_code": "600000.SH"},
            kline_series_id=5,
        )

    assert results.deleted == []
    assert returns.deleted == []


def test_require_e12_reports_missing_endpoint():
    api = FakeApi(
        links=FakeController(
            fail_list=RemoteApiError("远程数据服务 HTTP 404: ")
        )
    )

    with pytest.raises(RemoteApiError) as exc:
        require_e12(api)

    assert "E12" in str(exc.value)
    assert "ParamTaskResultKlineLinks" in str(exc.value)


class _FakeTokenEntity:
    def __init__(self):
        self.id = None

    def to_dict(self):
        return {
            "id": None,
            "name": "probe",
            "task_type": "google_sheet",
            "is_active": True,
        }


def test_token_add_entity_writes_back_generated_id():
    tokens = FakeController(insert=(None, 9))
    repo = GoogleSheetTokenHttpRepository(api=FakeApi(tokens=tokens))
    entity = _FakeTokenEntity()

    repo.add_entity(entity)

    assert entity.id == 9
