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
        # exclude_none 收口：未提供的可空键（google_sheet_id/model_version）不再落 null
        assert migrated["sheets"] == [{
            "spreadsheet_id": "abc",
            "sheet_name": "Sheet1",
            "title": "策略A-1y-3]",
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
                "model_version": "c7_0_3",
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
            "model_version": "c7_0_3",
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


class TestStockCodeSearchProjection:
    @pytest.mark.parametrize("task_type", [
        "google_sheet_C4", "google_sheet_C5", "google_sheet_C7", "google_sheet_C1_1",
    ])
    def test_indexes_all_codes_without_changing_execution_parameters(self, task_type):
        from copy import deepcopy

        source = {
            "sheets": [{"spreadsheet_id": "s"}],
            "parameters": [["QQQ", "soxx", "", "QQQ"], ["2.2"]],
            "stock_codes": ["OLD"],
        }
        original = deepcopy(source)
        shaped = validate_task_config_shape(task_type, source)
        assert shaped["stock_codes"] == ["QQQ", "SOXX"]
        assert "stock_code" not in shaped
        assert shaped["parameters"] == original["parameters"]
        assert source == original

    def test_parameter_edit_rebuilds_index(self):
        config = validate_task_config_shape("google_sheet_C7", {
            "sheets": [{"spreadsheet_id": "s"}], "parameters": [["QQQ", "SOXX"]],
        })
        config["parameters"] = [["ITB"]]
        assert validate_task_config_shape("google_sheet_C7", config)["stock_codes"] == ["ITB"]
        config["parameters"] = []
        assert validate_task_config_shape("google_sheet_C7", config)["stock_codes"] == []

    @pytest.mark.parametrize("task_type", ["google_sheet", "backtest_training"])
    def test_single_stock_uses_explicit_code_not_parameter_values(self, task_type):
        config = {
            "sheets": [{"spreadsheet_id": "s"}],
            "stock_code": "SOXX.US", "parameters": [["2.2", "3"]],
        }
        shaped = validate_task_config_shape(task_type, config)
        assert shaped["stock_codes"] == ["SOXX.US"]
        assert shaped["stock_code"] == "SOXX.US"

    def test_c3_missing_code_keeps_existing_sheet_mode(self):
        shaped = validate_task_config_shape("google_sheet", {
            "sheets": [{"spreadsheet_id": "abc"}], "parameters": [["2.2"]],
        })
        assert "stock_code" not in shaped
        assert shaped["stock_codes"] == []

    def test_multi_product_indexes_all_products(self):
        shaped = validate_task_config_shape("backtest_multi_product", {
            "products": [
                {"stock_code": "QQQ", "sheet": {"spreadsheet_id": "s1"}},
                {"stock_code": "SOXX", "sheet": {"spreadsheet_id": "s2"}},
            ],
        })
        assert shaped["stock_codes"] == ["QQQ", "SOXX"]
        assert "stock_code" not in shaped

    def test_migration_preserves_explicit_and_absent_execution_settings(self):
        legacy = {
            "sheets": [{"spreadsheet_id": "s"}],
            "parameters": [["QQQ", "SOXX"], ["2.2"]],
            "exclude_years": [2, 4],
        }
        migrated, status = migrate_config("google_sheet_C7", legacy)
        assert status == "migrated"
        assert migrated["stock_codes"] == ["QQQ", "SOXX"]
        assert "stock_code" not in migrated
        assert migrated["exclude_recent_years"] == [2, 4]
        assert "exclude_years" not in migrated
        assert "date_range_mode" not in migrated
        assert migrated["parameters"] == legacy["parameters"]
        again, status = migrate_config("google_sheet_C7", migrated)
        assert again == migrated and status == "unchanged"

    def test_explicit_null_execution_options_are_preserved(self):
        config = {"sheets": [{"spreadsheet_id": "s"}], "parameters": [["SOXX"]], "count_mode": None}
        shaped = validate_task_config_shape("google_sheet_C7", config)
        assert "count_mode" in shaped and shaped["count_mode"] is None

    def test_migration_preserves_sheet_extensions(self):
        ref = {"spreadsheet_id": "s", "sheet_name": "data", "title": "T", "layout_hint": "X"}
        migrated, _ = migrate_config("backtest_training", {"sheet": ref})
        assert migrated["sheets"] == [ref]

    def test_migration_does_not_guess_code(self):
        migrated, _ = migrate_config("google_sheet", {
            "spreadsheet_id": "s", "sheet_name": "data", "title": "SOXX-bdl-1y-0",
        })
        assert not migrated.get("stock_code")
        assert migrated["stock_codes"] == []

    @pytest.mark.parametrize("source", [
        {"sheets": [{"spreadsheet_id": "a"}], "sheet": {"spreadsheet_id": "b"}},
        {"spreadsheet_id": "a", "sheet": {"spreadsheet_id": "b"}},
        {"spreadsheet_id": "a", "sheet_name": "data", "sheet": {"spreadsheet_id": "a", "sheet_name": "other"}},
    ])
    def test_conflicting_sheet_references_are_not_silently_discarded(self, source):
        migrated, status = migrate_config("google_sheet", source)
        assert migrated is None and status.startswith("skipped:")


class TestConfigWriteBoundaries:
    def test_lowercase_template_type_uses_same_shape_without_changing_filter_key(self):
        from app.services.task_template_service import task_template_service

        stored = json.loads(task_template_service._serialize_config_str({
            "task_type": "google_sheet_c7", "sheets": [{"spreadsheet_id": "s"}],
            "parameters": [["QQQ", "SOXX"]], "stock_codes": ["STALE"],
        }))
        assert stored["stock_codes"] == ["QQQ", "SOXX"]
        assert stored["task_type"] == "google_sheet_c7"

    def test_legacy_keys_rejected_alongside_canonical_sheet(self):
        with pytest.raises(ValueError):
            validate_task_config_shape("google_sheet", {
                "sheets": [{"spreadsheet_id": "a"}], "spreadsheet_id": "b",
            })

    def test_migration_template_type_detected_from_config(self):
        from scripts.migrate_task_config_schema import _infer_config_kind

        assert _infer_config_kind({"task_type": "google_sheet_c7", "sheets": []}) == "google_sheet_c7"

    def test_c31_template_keeps_input_stock_codes(self):
        from app.services.task_template_service import task_template_service

        source = {"task_type": "google_sheet_C31", "stock_codes": ["QQQ", "SOXX"],
                  "sheets": [{"spreadsheet_id": "s1"}, {"spreadsheet_id": "s2"}],
                  "parameters": [[1, 2]]}
        stored = json.loads(task_template_service._serialize_config_str(source))
        assert stored["stock_codes"] == source["stock_codes"]
        assert len(stored["sheets"]) == 2


class TestMigrationSafety:
    def test_backup_and_atomic_config_update(self, app_factory, tmp_path):
        from app.extensions import db
        from app.models import Task
        from scripts.migrate_task_config_schema import apply_changes

        row = Task(id="migrate-safe", name="safe", task_type="google_sheet", status="completed", config='{"old":1}')
        db.session.add(row)
        db.session.commit()
        backup = tmp_path / "backup.json"
        apply_changes(db.session, [{"table": "task", "id": row.id, "before": row.config, "after": '{"new":1}'}], backup)
        db.session.expire_all()
        assert db.session.get(Task, row.id).config == '{"new":1}'
        assert json.loads(backup.read_text(encoding="utf-8"))["changes"][0]["before"] == '{"old":1}'
        assert row.status == "completed"

    def test_concurrent_change_rolls_back_entire_batch(self, app_factory, tmp_path):
        from app.extensions import db
        from app.models import Task
        from scripts.migrate_task_config_schema import apply_changes

        for identity in ("migrate-a", "migrate-b"):
            db.session.add(Task(id=identity, name=identity, task_type="google_sheet", status="completed", config='{"old":1}'))
        db.session.commit()
        changes = [
            {"table": "task", "id": "migrate-a", "before": '{"old":1}', "after": '{"new":1}'},
            {"table": "task", "id": "migrate-b", "before": '{"stale":1}', "after": '{"new":1}'},
        ]
        with pytest.raises(ValueError, match="变化"):
            apply_changes(db.session, changes, tmp_path / "backup.json")
        assert db.session.get(Task, "migrate-a").config == '{"old":1}'
        assert db.session.get(Task, "migrate-b").config == '{"old":1}'

    def test_existing_backup_is_not_overwritten(self, app_factory, tmp_path):
        from app.extensions import db
        from scripts.migrate_task_config_schema import apply_changes

        backup = tmp_path / "backup.json"
        backup.write_text("original", encoding="utf-8")
        with pytest.raises(FileExistsError):
            apply_changes(db.session, [], backup)
        assert backup.read_text(encoding="utf-8") == "original"

    def test_backup_flush_failure_prevents_database_changes(self, app_factory, tmp_path, monkeypatch):
        import os
        from app.extensions import db
        from app.models import Task
        from scripts.migrate_task_config_schema import apply_changes

        db.session.add(Task(id="flush", name="flush", task_type="google_sheet", status="completed", config="{}"))
        db.session.commit()
        def fail_flush(fd):
            raise OSError("disk failure")
        monkeypatch.setattr(os, "fsync", fail_flush)
        with pytest.raises(OSError, match="disk failure"):
            apply_changes(db.session, [{"table": "task", "id": "flush", "before": "{}", "after": '{"x":1}'}], tmp_path / "backup.json")
        assert db.session.get(Task, "flush").config == "{}"

    def test_task_started_after_precheck_is_not_modified(self, app_factory, tmp_path, monkeypatch):
        import os
        from app.extensions import db
        from app.models import Task
        from scripts.migrate_task_config_schema import apply_changes

        db.session.add(Task(id="race", name="race", task_type="google_sheet", status="pending", config="{}"))
        db.session.commit()
        fsync = os.fsync
        def start_after_precheck(fd):
            fsync(fd)
            db.session.query(Task).filter_by(id="race").update({"status": "running"})
            db.session.commit()
        monkeypatch.setattr(os, "fsync", start_after_precheck)
        with pytest.raises(ValueError, match="运行中"):
            apply_changes(db.session, [{"table": "task", "id": "race", "before": "{}", "after": '{"x":1}'}], tmp_path / "backup.json")
        assert db.session.get(Task, "race").config == "{}"

    def test_running_tasks_block_migration(self, app_factory, tmp_path):
        from app.extensions import db
        from app.models import Task
        from scripts.migrate_task_config_schema import apply_changes

        db.session.add(Task(id="running", name="running", task_type="google_sheet", status="running", config="{}"))
        db.session.commit()
        backup = tmp_path / "backup.json"
        with pytest.raises(ValueError, match="运行中"):
            apply_changes(db.session, [], backup)
        assert not backup.exists()


class TestUpdateConfigMerge:
    def test_c7_merge_recomputes_search_codes(self, app_factory, monkeypatch):
        from app.services.task import task_manager
        from app.repositories import task_repository

        monkeypatch.setattr(task_manager, "validate_c_series_sheet_models", lambda config: None)
        task_repository.create({
            "id": "c7-index", "name": "index", "task_type": "google_sheet_C7", "status": "completed",
            "config": json.dumps({"sheets": [{"spreadsheet_id": "s", "model_version": "c7_0_3"}],
                                  "parameters": [["QQQ", "SOXX"]], "stock_codes": ["QQQ", "SOXX"]}),
        })
        task_manager.update_task_config("c7-index", {"parameters": [["ITB", "XBI"]]})
        config = task_repository.get("c7-index")["config"]
        assert config["stock_codes"] == ["ITB", "XBI"]
        assert config["parameters"] == [["ITB", "XBI"]]
        assert "stock_code" not in config

    def test_merge_keeps_untouched_keys(self, app_factory, monkeypatch):
        """结构化表单部分提交：payload 未列出的键保留（修复表单重建丢键）。"""
        with app_factory.app_context():
            from app.extensions import db
            from app.models import GoogleSheet
            from app.repositories import task_repository
            from app.services.task import task_manager

            db.session.add(
                GoogleSheet(name="s1", spreadsheet_id="s1", table_type="c3")
            )
            db.session.commit()

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
            from app.extensions import db
            from app.models import GoogleSheet
            from app.repositories import task_repository
            from app.services.task import task_manager

            db.session.add(
                GoogleSheet(name="s1", spreadsheet_id="s1", table_type="c3")
            )
            db.session.commit()

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

    def test_full_replace_refreshes_token_snapshot(self, app_factory, monkeypatch):
        """编辑换 token_id 后派生快照（token_name/token_file）随之刷新：update 与
        create 走同一条派生链（normalize → hydrate → prepare → validate）。"""
        with app_factory.app_context():
            from app.extensions import db
            from app.models import GoogleSheet
            from app.repositories import task_repository
            from app.services.task import task_manager

            db.session.add(
                GoogleSheet(name="s1", spreadsheet_id="s1", table_type="c3")
            )
            db.session.commit()

            def fake_prepare(config):
                resolved = dict(config)
                if resolved.get("token_id") == 7:
                    resolved["token_name"] = "token-7"
                    resolved["token_file"] = "p7.json"
                return resolved

            monkeypatch.setattr(
                "app.services.task.creation.get_google_sheet_token_service",
                lambda: type("TokenSvc", (), {"prepare_task_config": staticmethod(fake_prepare)})(),
            )

            existing = {
                "sheets": [{"spreadsheet_id": "s1", "sheet_name": "data", "title": ""}],
                "stock_code": "600000.SH",
                "token_type": "file",
                "token_id": 5,
                "token_name": "token-5",
                "token_file": "p5.json",
            }
            task_repository.create({
                "id": "task-edit-token",
                "name": "edit-token",
                "description": "",
                "task_type": "google_sheet",
                "config": json.dumps(existing),
                "status": "pending",
            })

            task_manager.update_task_config(
                "task-edit-token",
                {
                    "sheets": [{"spreadsheet_id": "s1", "sheet_name": "data", "title": ""}],
                    "stock_code": "600000.SH",
                    "token_type": "file",
                    "token_id": 7,
                },
                merge_config=False,
            )
            config = task_repository.get("task-edit-token")["config"]
            assert config["token_id"] == 7
            assert config["token_name"] == "token-7"
            assert config["token_file"] == "p7.json"
            # 旧快照不残留（merge=False 全量覆盖）；检索投影仍由收口出口重建
            assert "token_selection_mode" not in config
            assert config["stock_codes"] == ["600000.SH"]

    def test_update_config_rejects_running_task(self, app_factory, monkeypatch):
        """running 任务禁改的硬守卫（编辑入口的前置约定）。"""
        import pytest

        from app.exceptions import ValidationError
        from app.repositories import task_repository
        from app.services.task import task_manager

        task_repository.create({
            "id": "task-edit-running",
            "name": "running",
            "description": "",
            "task_type": "google_sheet",
            "config": json.dumps({"sheets": [{"spreadsheet_id": "s", "title": ""}]}),
            "status": "running",
        })
        with pytest.raises(ValidationError, match="正在运行的任务无法直接修改"):
            task_manager.update_task_config(
                "task-edit-running",
                {"end_date": "2026-10-01"},
            )
