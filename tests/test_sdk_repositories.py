from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.repositories.config_repository import SystemConfigRepository
from app.repositories.google_sheet_repository import GoogleSheetRepository
from app.repositories.google_sheet_token_repository import GoogleSheetTokenRepository
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.repositories.sdk_client import (
    SdkConfigurationError,
    SdkDataAccessError,
    SdkDuplicateKeyError,
    SdkOperationError,
    SdkProtocolError,
    StockSdkAdapter,
)
from app.repositories.stock_metadata_repository import StockMetadataRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.task_log_repository import TaskLogRepository
from app.repositories.task_result_repository import TaskResultRepository
from app.repositories.task_result_return_repository import TaskResultReturnRepository
from app.repositories.backtest_sheet_run_lock_repository import BacktestSheetRunLockRepository
from app.repositories.backtest_product_result_cache_repository import BacktestProductResultCacheRepository
from app.repositories.task_result_summary_index_repository import TaskResultSummaryIndexRepository
from app.repositories.template_repository import TaskTemplateRepository
from app.services.config_manager import ConfigManager
from app.services.google_sheet_token_service import GoogleSheetTokenService
from app.services.stock_metadata_service import save_stock_metadata
from app.services.google_sheet_registry_service import GoogleSheetRegistryService
from stock_sdk.exceptions import ApiHttpError, ApiTimeoutError
from stock_sdk.response import ResponseDto


class FakeGroup:
    """模拟生成 SDK 的一个资源分组，并记录请求载荷供断言使用。"""
    def __init__(self, response: ResponseDto | Exception):
        self.response = response
        self.calls = []

    def _return(self, payload):
        self.calls.append(payload)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    def get_data_by_page_list(self, payload):
        return self._return(payload)

    def get_info_by_id(self, payload):
        return self._return(payload)

    def modify_or_add(self, payload):
        return self._return(payload)

    def delete(self, payload):
        return self._return(payload)


def adapter_for(group_name: str, response: ResponseDto | Exception):
    """构造仅包含指定资源分组的 SDK 适配器测试替身。"""
    client = SimpleNamespace(**{group_name: FakeGroup(response)})
    return StockSdkAdapter(client), getattr(client, group_name)


class SdkRepositoryTests(unittest.TestCase):
    def test_every_repository_unwraps_and_normalizes_sdk_records(self):
        """各 Repository 都应解包 ret_obj 并完成自身字段标准化。"""
        cases = [
            (SystemConfigRepository, "param_system_configs", {"id": 1, "key": "feature", "value": "true"}, {"key": "feature"}),
            (TaskTemplateRepository, "param_task_templates", {"id": 1, "name": "C3", "config": '{"task_type": "c3"}'}, {"config": {"task_type": "c3"}}),
            (StockMetadataRepository, "param_stock_metadata", {"id": 1, "stock_code": "000001", "raw_json": '{"code": "000001"}'}, {"raw": {"code": "000001"}}),
            (GoogleSheetRepository, "param_google_sheet", {"id": 1, "is_active": 1, "is_in_use": 0}, {"is_active": True, "is_in_use": False}),
            (GoogleSheetTokenRepository, "param_google_sheet_tokens", {"id": 1, "is_active": 1, "token_context": "secret"}, {"is_active": True}),
            (ScheduledTaskRepository, "param_scheduled_tasks", {"id": 1, "is_active": 1, "is_running": 0, "task_params": '{"days": 7}'}, {"is_active": True, "is_running": False, "task_params": {"days": 7}}),
            (TaskRepository, "param_tasks", {"id": "task-1", "config": '{"source": "test"}'}, {"id": "task-1", "config": {"source": "test"}}),
            (TaskLogRepository, "param_task_logs", {"id": 1, "task_id": "task-1", "message": "ok"}, {"task_id": "task-1"}),
            (TaskResultRepository, "param_task_results", {"id": 1, "parameters": '{"p": 1}', "result": '{"r": 2}', "success": 1}, {"parameters": {"p": 1}, "result": {"r": 2}, "success": True}),
            (TaskResultReturnRepository, "param_task_results_return", {"id": 1, "returns_json": '{"dates": []}'}, {"returns_json": {"dates": []}}),
            (BacktestSheetRunLockRepository, "param_backtest_sheet_run_locks", {"id": 1, "spreadsheet_id": "sheet"}, {"spreadsheet_id": "sheet"}),
            (BacktestProductResultCacheRepository, "param_backtest_product_result_cache", {"id": 1, "result_json": '{"v": 1}'}, {"result_json": {"v": 1}}),
            (TaskResultSummaryIndexRepository, "param_task_result_summary_index", {"id": 1, "metrics_json": '{"x": 1}', "is_best": 1}, {"metrics_json": {"x": 1}, "is_best": True}),
        ]
        for repository_class, group_name, record, expected in cases:
            with self.subTest(repository=repository_class.__name__):
                adapter, group = adapter_for(group_name, ResponseDto(ret_code=200, ret_obj=record))
                repository = repository_class(adapter)
                record_id = record["id"]
                self.assertGreaterEqual(repository.get(record_id).items(), expected.items())
                self.assertEqual(group.calls, [{"id": record_id}])
                group.response = ResponseDto(ret_code=200, ret_obj={"items": [record], "total": 1})
                self.assertEqual(repository.list_page()["total"], 1)
                group.response = ResponseDto(ret_code=200, ret_obj=record)
                self.assertIsInstance(repository.save(record), dict)
                group.response = ResponseDto(ret_code=200, ret_obj={})
                repository.delete(record_id)
                self.assertEqual(group.calls[-1], {"id": record_id})

    def test_template_repository_serializes_payload_and_parses_page(self):
        """模板 Repository 应正确处理 config 的 JSON 双向转换。"""
        adapter, group = adapter_for(
            "param_task_templates",
            ResponseDto(ret_code=200, ret_obj={"items": [{"id": 8, "config": "{}"}], "total": 1}),
        )
        repository = TaskTemplateRepository(adapter)

        self.assertEqual(repository.list_page(order_field="created_at", order_type="desc"), {"items": [{"id": 8, "config": {}}], "total": 1})
        self.assertEqual(group.calls[0]["page_index"], 1)

        group.response = ResponseDto(ret_code=200, ret_obj={"id": 8, "config": "{}"})
        repository.save({"id": 8, "name": "template", "config": {"task_type": "c3"}})
        self.assertEqual(group.calls[-1]["config"], '{"task_type": "c3"}')

    def test_save_accepts_success_response_without_ret_obj(self):
        """仅含成功信封的 ModifyOrAdd 不应被误判为协议错误。"""
        adapter, group = adapter_for(
            "param_task_templates",
            ResponseDto(ret_code=200, ret_msg="请求(或处理)成功", ret_count=22),
        )

        saved = TaskTemplateRepository(adapter).save({
            "name": "C3 模板",
            "description": "测试",
            "config": {"task_type": "c3"},
        })

        self.assertEqual(saved, {
            "name": "C3 模板",
            "description": "测试",
            "config": {"task_type": "c3"},
        })
        self.assertEqual(group.calls[-1]["config"], '{"task_type": "c3"}')

    def test_adapter_raises_for_business_failure_without_leaking_response(self):
        """远端业务失败应转换为领域异常，不能向服务层泄露 SDK 响应。"""
        adapter, _ = adapter_for("param_system_configs", ResponseDto(ret_code=400, ret_msg="invalid request"))
        with self.assertRaisesRegex(SdkOperationError, "invalid request"):
            adapter.call("param_system_configs", "get_info_by_id", {"id": 1})

    def test_adapter_maps_duplicate_key_to_typed_error(self):
        """唯一约束冲突必须显式返回，调用方不得覆盖已有远端记录。"""
        adapter, _ = adapter_for(
            "param_backtest_sheet_run_locks",
            ResponseDto(ret_code=409, ret_msg="DUPLICATE_KEY spreadsheet_id"),
        )
        with self.assertRaises(SdkDuplicateKeyError):
            adapter.call("param_backtest_sheet_run_locks", "modify_or_add", {"spreadsheet_id": "sheet"})

    def test_task_repository_keeps_string_task_id_and_serializes_config(self):
        """任务 UUID 不能被通用 Repository 强制转换为数字主键。"""
        adapter, group = adapter_for(
            "param_tasks",
            ResponseDto(ret_code=200, ret_obj={"id": "task-1", "status": "pending", "config": "{}"}),
        )
        repository = TaskRepository(adapter)
        task = repository.get("task-1")
        self.assertEqual(task["id"], "task-1")
        # 兼容尚未完全改造的旧服务，远程任务 DTO 仍支持属性访问和序列化。
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.to_dict()["id"], "task-1")
        repository.save({"id": "task-1", "config": {"a": 1}})
        self.assertEqual(group.calls[-1]["config"], '{"a": 1}')

    def test_backtest_sheet_lock_uses_duplicate_key_and_ownership_check(self):
        """回测锁在冲突时不覆盖既有记录，释放前必须校验任务归属。"""
        from app.services.task.facade import TaskManager
        from app.services.task import runtime

        class FakeLockRepository:
            def __init__(self):
                self.records = {}
                self.deleted = []

            def save(self, payload):
                if payload.get("spreadsheet_id") == "occupied":
                    raise SdkDuplicateKeyError("DUPLICATE_KEY", code=409)
                record = {**payload, "id": 9}
                self.records[9] = record
                return record

            def get(self, record_id):
                return self.records.get(record_id)

            def delete(self, record_id):
                self.deleted.append(record_id)
                self.records.pop(record_id, None)

        original = runtime._backtest_sheet_lock_repository
        fake_repository = FakeLockRepository()
        runtime._backtest_sheet_lock_repository = fake_repository
        try:
            manager = TaskManager()
            self.assertEqual(manager._acquire_backtest_sheet_run_lock("sheet", "task-a", task_type="backtest_training"), (True, None))
            self.assertEqual(manager._acquire_backtest_sheet_run_lock("occupied", "task-b", task_type="backtest_training"), (False, None))
            manager._release_backtest_sheet_run_reservation("sheet", "task-a")
            self.assertEqual(fake_repository.deleted, [9])
        finally:
            runtime._backtest_sheet_lock_repository = original

    def test_c31_creation_failure_compensates_remote_child_tasks(self):
        """C31 第二个子任务创建失败时，应删除此前已创建的远程任务。"""
        from app.services.task.facade import TaskManager

        class FakeTaskManager(TaskManager):
            def __init__(self):
                super().__init__()
                self.create_calls = 0
                self.deleted_task_ids = []

            def create_task(self, *_args, **_kwargs):
                self.create_calls += 1
                if self.create_calls == 2:
                    raise SdkDataAccessError("远程数据服务暂不可用")
                return "child-task-1"

            def start_task(self, _task_id):
                return True

            def delete_task(self, task_id):
                self.deleted_task_ids.append(task_id)
                return True

        manager = FakeTaskManager()
        data = {
            "config": {
                "base_task_name": "批量策略",
                "stock_codes": ["000001"],
                "parameters": [[[1], [2]]],
                "sheets": [
                    {"spreadsheet_id": "sheet-1", "sheet_name": "A", "title": "策略-1y-1]"},
                    {"spreadsheet_id": "sheet-2", "sheet_name": "B", "title": "策略-1y-2]"},
                ],
            },
        }
        with patch("app.services.task.creation.time.sleep"):
            with self.assertRaises(SdkDataAccessError):
                manager.batch_create_and_start_task(data)
        self.assertEqual(manager.deleted_task_ids, ["child-task-1"])

    def test_adapter_maps_transport_failures(self):
        """网络与 HTTP 失败应统一映射为数据访问异常。"""
        for error in (ApiTimeoutError("timeout"), ApiHttpError(502, {"error": "bad gateway"})):
            with self.subTest(error=error.__class__.__name__):
                adapter, _ = adapter_for("param_system_configs", error)
                with self.assertRaisesRegex(SdkDataAccessError, "远程数据服务暂不可用"):
                    adapter.call("param_system_configs", "get_info_by_id", {"id": 1})

    def test_adapter_rejects_empty_or_malformed_sdk_data(self):
        """不符合 SDK 协议的响应必须显式失败。"""
        adapter, _ = adapter_for("param_system_configs", ResponseDto(ret_code=200, ret_obj=None))
        with self.assertRaisesRegex(SdkProtocolError, "分页结果不是对象"):
            SystemConfigRepository(adapter).list_page()

    def test_adapter_requires_configured_base_url(self):
        """未配置远端地址时不应隐式使用默认地址。"""
        import os

        original_value = os.environ.pop("STOCK_BASE_URL", None)
        try:
            with self.assertRaisesRegex(SdkConfigurationError, "STOCK_BASE_URL"):
                StockSdkAdapter._build_client()
        finally:
            if original_value is not None:
                os.environ["STOCK_BASE_URL"] = original_value

    def test_google_sheet_registry_uses_repository_for_plain_crud(self):
        """Sheet 注册表的普通增删查应经 Repository 访问远端。"""
        class FakeGoogleSheetRepository:
            def __init__(self):
                self.items = [{
                    "id": 1,
                    "name": "C3 Sheet",
                    "spreadsheet_id": "sheet-1",
                    "table_type": "c3",
                    "registry_scope": "c3",
                    "is_active": True,
                    "is_in_use": False,
                }]
                self.saved = []
                self.deleted = []

            def list_page(self, **_kwargs):
                return {"items": list(self.items), "total": len(self.items)}

            def get(self, record_id):
                return next((item for item in self.items if item["id"] == record_id), None)

            def save(self, payload):
                self.saved.append(dict(payload))
                return dict(payload)

            def delete(self, record_id):
                self.deleted.append(record_id)

        repository = FakeGoogleSheetRepository()
        service = GoogleSheetRegistryService(repository=repository)

        self.assertEqual(service.list_sheets(), repository.items)
        created = service.create_sheet("sheet-2", name="C4 Sheet", table_type="c4")
        self.assertEqual(created["registry_scope"], "c_series")
        self.assertEqual(repository.saved[-1]["spreadsheet_id"], "sheet-2")
        service.delete_sheet(1)
        self.assertEqual(repository.deleted, [1])

    def test_config_manager_uses_system_config_repository(self):
        """配置管理器的读取与普通写入应委托系统配置 Repository。"""
        class FakeSystemConfigRepository:
            def __init__(self):
                self.records = [{"id": 1, "key": "limit", "value": "5", "description": "old"}]
                self.saved = []
                self.deleted = []

            def list_all(self):
                return list(self.records)

            def get_by_key(self, key):
                return next((item for item in self.records if item["key"] == key), None)

            def save(self, payload):
                saved = dict(payload)
                saved.setdefault("id", 2)
                self.saved.append(saved)
                return saved

            def delete(self, record_id):
                self.deleted.append(record_id)

        from flask import Flask

        repository = FakeSystemConfigRepository()
        manager = ConfigManager(repository=repository)
        manager.init_app(Flask(__name__))
        self.assertEqual(manager.get_config("limit"), "5")
        self.assertTrue(manager.set_config("limit", 6, "new"))
        self.assertEqual(repository.saved[-1], {"id": 1, "key": "limit", "value": "6", "description": "new"})
        self.assertTrue(manager.delete_config("limit"))
        self.assertEqual(repository.deleted, [1])

    def test_token_detail_read_uses_repository_without_usage_reconciliation(self):
        """Token 详情读取不应触发本地占用次数重算。"""
        class FakeTokenRepository:
            def get(self, record_id):
                return {"id": record_id, "name": "token", "is_active": 1, "token_context": "secret"}

            def public_record(self, record, *, include_context=False):
                result = dict(record)
                if not include_context:
                    result.pop("token_context", None)
                return result

        service = GoogleSheetTokenService(repository=FakeTokenRepository())
        self.assertEqual(service.get_token(3), {"id": 3, "name": "token", "is_active": 1})

    def test_token_plain_list_and_update_use_remote_repository(self):
        """Token 无筛选列表和常规更新应经远程 Repository。"""
        class FakeTokenRepository:
            def __init__(self):
                self.saved = []

            def list_public(self):
                return [{"id": 1, "name": "token", "is_active": True}]

            def get(self, record_id):
                return {
                    "id": record_id,
                    "name": "old",
                    "task_type": "google_sheet",
                    "token_file": "data/token.json",
                    "token_context": '{"refresh_token": "x"}',
                    "is_active": True,
                }

            def save(self, payload):
                self.saved.append(dict(payload))
                return dict(payload)

            def public_record(self, record, *, include_context=False):
                result = dict(record)
                result.pop("token_context", None)
                return result

        repository = FakeTokenRepository()
        service = GoogleSheetTokenService(repository=repository)
        self.assertEqual(service.list_tokens(), [{"id": 1, "name": "token", "is_active": True}])
        result = service.update_token(1, name="new", is_active=False)
        self.assertEqual(result["name"], "new")
        self.assertFalse(repository.saved[-1]["is_active"])

    def test_token_filtered_list_requires_documented_remote_filter(self):
        """未声明 task_type 筛选时，禁止通过拉全量数据模拟筛选。"""
        class FakeTokenRepository:
            def list_public(self):
                return []

        from app.repositories.sdk_client import SdkFilterUnavailableError

        with self.assertRaises(SdkFilterUnavailableError):
            GoogleSheetTokenService(repository=FakeTokenRepository()).list_tokens("backtest_training")

    def test_stock_metadata_remote_save_normalizes_raw_payload(self):
        """股票元数据远程保存前应规范化字段及原始数据。"""
        class FakeMetadataRepository:
            def save_metadata(self, payload):
                return payload

        from app.services import stock_metadata_service

        original = stock_metadata_service._remote_repository
        stock_metadata_service._remote_repository = FakeMetadataRepository()
        try:
            result = save_stock_metadata({
                "id": 7,
                "code": "600519",
                "name": "贵州茅台",
                "market_type": "cn",
                "raw": {"source": "test"},
            })
        finally:
            stock_metadata_service._remote_repository = original
        self.assertEqual(result["id"], 7)
        self.assertIn('"source": "test"', result["raw_json"])
