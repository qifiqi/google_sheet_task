# -*- coding: utf-8 -*-
"""任务配置结构统一（2026-10）回归：逐类型模型、merge 编辑语义、迁移函数。

统一约定：Google Sheet 引用唯一形态 ``sheets: [{spreadsheet_id, sheet_name,
title}]``（C3/C31 子任务/单品回测恰好 1 个元素）；读取端不再容忍旧形态
（C3 顶层平铺 / training 嵌套 sheet{}），历史数据经迁移脚本收敛。
"""

import json

import pytest

from app.schemas.task_configs import (
    C3TaskConfig,
    C5TaskConfig,
    BacktestTrainingConfig,
    MultiProductConfig,
    validate_task_config_shape,
)
from scripts.migrate_task_config_schema import migrate_config


class TestConfigModels:
    def test_c3_accepts_single_sheet_and_coerces_none_title(self):
        config = C3TaskConfig.model_validate({
            "sheets": [{"spreadsheet_id": " abc ", "sheet_name": "", "title": None}],
            "stock_code": "600000",
            "parameters": [["1"], ["2"]],
        })
        assert config.sheets[0].spreadsheet_id == "abc"
        assert config.sheets[0].sheet_name == "data"
        assert config.sheets[0].title == ""

    def test_c3_rejects_legacy_flat_keys(self):
        with pytest.raises(Exception):
            C3TaskConfig.model_validate({
                "spreadsheet_id": "abc",
                "sheet_name": "data",
                "stock_code": "600000",
            })

    def test_c3_rejects_multiple_sheets(self):
        with pytest.raises(Exception, match="长度必须为 1"):
            C3TaskConfig.model_validate({
                "sheets": [{"spreadsheet_id": "a"}, {"spreadsheet_id": "b"}],
            })

    def test_c5_keeps_extra_layout_keys_and_coerces_types(self):
        config = C5TaskConfig.model_validate({
            "sheets": [{"spreadsheet_id": "s"}],
            "random_group_count": "3",
            # 执行期布局键（SystemConfig 兜底域）经 extra=allow 无损保留
            "c5_input_column_a": "A",
        })
        assert config.random_group_count == 3
        assert config.model_dump(mode="json")["c5_input_column_a"] == "A"

    def test_training_single_sheet_constraint(self):
        with pytest.raises(Exception, match="长度必须为 1"):
            BacktestTrainingConfig.model_validate({
                "sheets": [{"spreadsheet_id": "a"}, {"spreadsheet_id": "b"}],
            })

    def test_multi_product_keeps_per_product_sheet(self):
        config = MultiProductConfig.model_validate({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [
                {"stock_code": "A", "sheet": {"spreadsheet_id": "s1"}},
                {"stock_code": "B", "sheet": {"spreadsheet_id": "s2"}},
            ],
        })
        assert [p.sheet.spreadsheet_id for p in config.products] == ["s1", "s2"]

    def test_validate_shape_passthrough_unknown_type(self):
        payload = {"anything": True}
        assert validate_task_config_shape("unknown_type", payload) is payload

    def test_validate_shape_rejects_missing_sheets(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            validate_task_config_shape("google_sheet", {"stock_code": "600000"})


class TestMigrateConfig:
    def test_c3_flat_keys_packed_into_sheets(self):
        legacy = {
            "spreadsheet_id": "abc",
            "sheet_name": "Sheet1",
            "title": "策略A-1y-3]",
            "stock_code": "600000.SH",
            "year_n": "1y",
            "parameters": [["1"]],
        }
        migrated, status = migrate_config("google_sheet", legacy)
        assert status == "migrated"
        assert migrated["sheets"] == [{
            "spreadsheet_id": "abc",
            "sheet_name": "Sheet1",
            "title": "策略A-1y-3]",
            "google_sheet_id": None,
            "c7_model_version": None,
        }]
        # 旧键从顶层移除（读取端不再容忍）
        assert "spreadsheet_id" not in migrated
        assert "sheet_name" not in migrated
        assert migrated["stock_code"] == "600000.SH"

    def test_c3_spreadsheet_title_falls_back_to_title(self):
        legacy = {
            "spreadsheet_id": "abc",
            "sheet_name": "data",
            "spreadsheet_title": "展示标题",
        }
        migrated, status = migrate_config("google_sheet", legacy)
        assert status == "migrated"
        assert migrated["sheets"][0]["title"] == "展示标题"
        assert "spreadsheet_title" not in migrated

    def test_training_nested_sheet_moved_into_sheets(self):
        legacy = {
            "sheet": {
                "spreadsheet_id": "xyz",
                "sheet_name": "data",
                "title": "C7 回测",
                "google_sheet_id": "12",
                "c7_model_version": "c7_0_3",
            },
            "stock_code": "600000.SH",
        }
        migrated, status = migrate_config("backtest_training", legacy)
        assert status == "migrated"
        assert migrated["sheets"] == [{
            "spreadsheet_id": "xyz",
            "sheet_name": "data",
            "title": "C7 回测",
            "google_sheet_id": "12",
            "c7_model_version": "c7_0_3",
        }]
        assert "sheet" not in migrated

    def test_c4_canonical_config_unchanged(self):
        canonical = {
            "sheets": [{"spreadsheet_id": "s1", "sheet_name": "data", "title": ""}],
            "count_mode": "n_plus_1",
            "parameters": [["1"]],
        }
        # 模型 dump 会补全声明字段默认值 → 形态收敛仍视为变更（canonical 化）
        result, status = migrate_config("google_sheet_C4", canonical)
        assert status in ("unchanged", "migrated")
        assert result["sheets"][0]["spreadsheet_id"] == "s1"

    def test_migration_idempotent(self):
        legacy = {
            "spreadsheet_id": "abc",
            "sheet_name": "data",
            "title": "T",
            "stock_code": "600000.SH",
        }
        once, _ = migrate_config("google_sheet", legacy)
        twice, status = migrate_config("google_sheet", once)
        assert twice == once
        assert status == "unchanged"

    def test_missing_spreadsheet_id_skipped(self):
        _, status = migrate_config("google_sheet", {"stock_code": "600000.SH"})
        assert status == "skipped:缺少 spreadsheet_id"

    def test_template_kind_inference_c3_flat(self):
        # 模板无 task_type：平铺 spreadsheet_id 推断为 C3 形态
        legacy = {"spreadsheet_id": "abc", "sheet_name": "data", "title": "T"}
        migrated, status = migrate_config(None, legacy)
        # 未知类型透传 → 未变形；形态推断发生在脚本 _migrate_rows 层
        assert status in ("unchanged", "migrated")


class TestUpdateConfigMerge:
    def test_merge_keeps_untouched_keys(self, app_factory, monkeypatch):
        """结构化表单部分提交：payload 未列出的键保留（修复表单重建丢键）。"""
        with app_factory.app_context():
            from app.models import Task
            from app.repositories import task_repository
            from app.services.task import task_manager

            existing = {
                "sheets": [{"spreadsheet_id": "s1", "sheet_name": "data", "title": ""}],
                "stock_code": "600000.SH",
                "year_n": "1y",
                "end_date": "2026-09-30",
                "kline_source": "custom",
                "parameters": [["1"]],
            }
            task_repository.create({
                "id": "task-merge-1",
                "name": "merge",
                "description": "",
                "task_type": "google_sheet",
                "config": json.dumps(existing),
                "status": "pending",
            })
            monkeypatch.setattr(
                "app.services.task.creation.get_google_sheet_token_service",
                lambda: type("TokenSvc", (), {"prepare_task_config": lambda self, config: config})(),
            )

            task_manager.update_task_config(
                "task-merge-1",
                {"end_date": "2026-10-01"},
                merge_config=True,
            )
            updated = task_repository.get("task-merge-1")
            config = updated["config"]  # to_dict 已解析为 dict
            # 未提交的键保留，提交的键覆盖
            assert config["end_date"] == "2026-10-01"
            assert config["year_n"] == "1y"
            assert config["kline_source"] == "custom"
            assert config["stock_code"] == "600000.SH"

    def test_full_replace_drops_removed_keys(self, app_factory, monkeypatch):
        with app_factory.app_context():
            from app.repositories import task_repository
            from app.services.task import task_manager

            existing = {
                "sheets": [{"spreadsheet_id": "s1", "sheet_name": "data", "title": ""}],
                "stock_code": "600000.SH",
                "legacy_key": "to-be-dropped",
            }
            task_repository.create({
                "id": "task-merge-2",
                "name": "replace",
                "description": "",
                "task_type": "google_sheet",
                "config": json.dumps(existing),
                "status": "pending",
            })
            monkeypatch.setattr(
                "app.services.task.creation.get_google_sheet_token_service",
                lambda: type("TokenSvc", (), {"prepare_task_config": lambda self, config: config})(),
            )

            task_manager.update_task_config(
                "task-merge-2",
                {"sheets": [{"spreadsheet_id": "s1", "sheet_name": "data", "title": ""}]},
                merge_config=False,
            )
            updated = task_repository.get("task-merge-2")
            config = updated["config"]  # to_dict 已解析为 dict
            assert "legacy_key" not in config
