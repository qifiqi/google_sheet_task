"""随机价格K线快照：源/序列复用、结果关联、清理与读取。"""

import json
import random
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.exceptions import NotFoundError
from app.extensions import db
from app.models import (
    Task,
    TaskKlineSource,
    TaskRandomSeries,
    TaskResult,
    TaskResultKlineLink,
)
from app.repositories import task_kline_snapshot_repository, task_result_repository
from app.services.google_sheet_tasks.c1_1 import C1_1Service
from app.services.google_sheet_tasks.c7 import C7Service
from app.services.kline_service import KlineService
from app.services.task.data_cleanup import (
    clear_task_execution_data,
    delete_task_result_dependencies,
)
from app.services.task_kline_snapshot_service import task_kline_snapshot_service


def _rows(count=31):
    first = date(2026, 1, 1)
    return [
        {
            "stock_date": (first + timedelta(days=offset)).isoformat(),
            "open": 10.0,
            "high": 14.0,
            "low": 8.0,
            "close": 12.0,
            "data_source": "dfcf",
        }
        for offset in range(count)
    ]


def _get_or_create_source(
    *,
    task_id="task-snapshot",
    stock_code="600000",
    kline_key="2026-2025",
    rows=None,
):
    return task_kline_snapshot_service.get_or_create_source(
        task_id=task_id,
        stock_code=stock_code,
        stock_name="测试股票",
        market_type="cn",
        kline_key=kline_key,
        data_source="dfcf",
        adjust_type="forward",
        rows=rows if rows is not None else _rows(),
    )


def _get_or_create_series(
    source,
    *,
    task_id="task-snapshot",
    stock_code="600000",
    kline_key="2026-2025",
    random_group=1,
    random_price_range="high_low",
    rows=None,
):
    rows = rows if rows is not None else _rows()
    return task_kline_snapshot_service.get_or_create_series(
        source=source,
        task_id=task_id,
        stock_code=stock_code,
        kline_key=kline_key,
        random_group=random_group,
        price_mode="random_price",
        random_price_range=random_price_range,
        seed=f"{task_id}:{stock_code}:{kline_key}:{random_price_range}:{random_group}",
        rows=rows,
    )


def test_same_dataset_reuses_source_and_series(app_factory):
    with app_factory.app_context():
        first_source = _get_or_create_source()
        second_source = _get_or_create_source()
        assert second_source["id"] == first_source["id"]

        first_series = _get_or_create_series(first_source)
        second_series = _get_or_create_series(second_source)
        assert second_series["id"] == first_series["id"]

        first_rows = task_kline_snapshot_service.merge_rows(first_source, first_series)
        second_rows = task_kline_snapshot_service.merge_rows(second_source, second_series)
        assert second_rows == first_rows
        assert len(first_rows) == 31
        assert all(8.0 <= row["stock_val"] <= 14.0 for row in first_rows)
        assert first_rows[0]["stock_date"] == "2026-01-01"


def test_random_groups_share_source_but_have_distinct_values(app_factory):
    with app_factory.app_context():
        source = _get_or_create_source()
        first = _get_or_create_series(source, random_group=1)
        second = _get_or_create_series(source, random_group=2)

        assert first["source_id"] == second["source_id"] == source["id"]
        assert first["id"] != second["id"]

        first_values = [
            row["stock_val"]
            for row in task_kline_snapshot_service.merge_rows(source, first)
        ]
        second_values = [
            row["stock_val"]
            for row in task_kline_snapshot_service.merge_rows(source, second)
        ]
        assert first_values != second_values


def test_same_kline_key_for_different_stocks_does_not_collide(app_factory):
    with app_factory.app_context():
        first_source = _get_or_create_source(stock_code="600000")
        second_source = _get_or_create_source(stock_code="000001")

        assert first_source["id"] != second_source["id"]
        first_series = _get_or_create_series(first_source, stock_code="600000")
        second_series = _get_or_create_series(second_source, stock_code="000001")
        assert first_series["id"] != second_series["id"]


def test_integer_year_kline_key_is_stored_as_string(app_factory):
    """整年模式 kline_key 是 int 年份，varchar 列直接绑定会让 PG 报类型不匹配。"""
    with app_factory.app_context():
        source = _get_or_create_source(kline_key=2018)
        assert source["kline_key"] == "2018"
        assert _get_or_create_source(kline_key=2018)["id"] == source["id"]

        series = _get_or_create_series(source, kline_key=2018)
        assert series["kline_key"] == "2018"
        assert series["dataset_key"] == "2018:high_low:random-1"
        assert len(task_kline_snapshot_service.merge_rows(source, series)) == 31


def _create_task(task_id="task-snapshot"):
    task = Task(
        id=task_id,
        name=task_id,
        task_type="google_sheet_C7",
        status="completed",
        config="{}",
    )
    db.session.add(task)
    db.session.commit()
    return task


def _create_result(*, task_id="task-snapshot", series_id=None, step_index=0):
    parameters = {"stock_code": "600000"}
    if series_id:
        parameters["kline_series_id"] = series_id
    return task_result_repository.create_with_return(
        {
            "task_id": task_id,
            "step_index": step_index,
            "parameters": json.dumps(parameters),
            "result": "{}",
            "success": True,
        },
        kline_series_id=series_id,
    )


def test_result_link_is_created_with_task_result(app_factory):
    with app_factory.app_context():
        task = _create_task()
        source = _get_or_create_source()
        series = _get_or_create_series(source)

        result = _create_result(series_id=series["id"])

        link = TaskResultKlineLink.query.filter_by(result_id=result["id"]).one()
        assert link.series_id == series["id"]
        assert link.task_id == task.id
        detail = task_result_repository.get_with_task_type(result["id"])
        assert detail["kline_series_id"] == series["id"]


def test_non_random_result_has_no_link(app_factory):
    with app_factory.app_context():
        _create_task()
        result = _create_result()

        assert TaskResultKlineLink.query.filter_by(result_id=result["id"]).count() == 0
        detail = task_result_repository.get_with_task_type(result["id"])
        assert detail["kline_series_id"] is None


def test_get_series_detail_returns_rows_and_metadata(app_factory):
    with app_factory.app_context():
        _create_task()
        source = _get_or_create_source()
        series = _get_or_create_series(source)

        snapshot = task_kline_snapshot_service.get_series_detail(series["id"])

        assert snapshot["rows"] == task_kline_snapshot_service.merge_rows(source, series)
        assert snapshot["series"]["seed"] == series["seed"]
        assert snapshot["series"]["dataset_key"] == series["dataset_key"]
        assert "values_json" not in snapshot["series"]
        assert "dates_json" not in snapshot["source"]
        assert snapshot["source"]["stock_name"] == "测试股票"
        assert snapshot["source"]["row_count"] == 31


def test_list_task_snapshots_returns_metadata_without_values(app_factory):
    with app_factory.app_context():
        task = _create_task()
        source = _get_or_create_source()
        _get_or_create_series(source, random_group=1)
        _get_or_create_series(source, random_group=2)

        data = task_kline_snapshot_service.list_task_snapshots(task.id)
        items = data["items"]

        assert data["total"] == 2
        assert len(items) == 2
        assert all("values_json" not in item for item in items)
        assert {item["random_group"] for item in items} == {1, 2}
        assert all(item["stock_code"] == "600000" for item in items)
        assert all(item["stock_name"] == "测试股票" for item in items)
        assert all(item["row_count"] == 31 for item in items)


def test_list_task_snapshots_paginates(app_factory):
    with app_factory.app_context():
        task = _create_task(task_id="task-list-page")
        source = _get_or_create_source(task_id=task.id)
        for group in range(1, 4):
            _get_or_create_series(
                source, task_id=task.id, random_group=group
            )

        first = task_kline_snapshot_service.list_task_snapshots(
            task.id, page=1, per_page=2
        )
        second = task_kline_snapshot_service.list_task_snapshots(
            task.id, page=2, per_page=2
        )

        assert first["total"] == 3
        assert [item["random_group"] for item in first["items"]] == [1, 2]
        assert [item["random_group"] for item in second["items"]] == [3]


def test_export_csv_contains_header_and_rows(app_factory):
    with app_factory.app_context():
        _create_task()
        source = _get_or_create_source()
        series = _get_or_create_series(source)
        snapshot = task_kline_snapshot_service.get_series_detail(series["id"])

        filename, text = task_kline_snapshot_service.export_csv(snapshot)

        assert filename.endswith(".csv")
        assert ":" not in filename
        lines = text.splitlines()
        assert lines[0] == "stock_date,stock_val,open,high,low,close,vwap"
        assert "2026-01-01" in lines[1]


def test_get_series_detail_rejects_other_task(app_factory):
    with app_factory.app_context():
        _create_task()
        source = _get_or_create_source()
        series = _get_or_create_series(source)

        with pytest.raises(NotFoundError):
            task_kline_snapshot_service.get_series_detail(
                series["id"], task_id="other-task"
            )


def test_clear_task_execution_data_removes_snapshots_and_links(app_factory):
    with app_factory.app_context():
        task = _create_task()
        source = _get_or_create_source()
        series = _get_or_create_series(source)
        _create_result(series_id=series["id"])

        clear_task_execution_data(task.id)
        db.session.commit()

        assert TaskResultKlineLink.query.filter_by(task_id=task.id).count() == 0
        assert TaskRandomSeries.query.filter_by(task_id=task.id).count() == 0
        assert TaskKlineSource.query.filter_by(task_id=task.id).count() == 0


def test_expand_random_price_groups_persists_and_reuses_snapshot(app_factory):
    with app_factory.app_context():
        service = object.__new__(C7Service)
        service.task_id = "task-expand"
        combinations = [{
            "stock_code": "600000",
            "A1": 1,
            "B1": 2,
            "year": "2026-2025",
            "kline_key": "2026-2025",
        }]
        kline_map = {"2026-2025": _rows()}
        snapshot_meta = {
            "stock_name": "测试股票",
            "market_type": "cn",
            "data_source": "dfcf",
            "adjust_type": "forward",
        }

        expanded, series_map = service._expand_random_price_groups(
            combinations,
            kline_map,
            "random_price",
            "high_low",
            2,
            snapshot_meta=snapshot_meta,
        )

        assert len(expanded) == 2
        assert all(item["kline_series_id"] for item in expanded)
        assert len({item["kline_series_id"] for item in expanded}) == 2
        assert TaskKlineSource.query.filter_by(task_id=service.task_id).count() == 1
        assert TaskRandomSeries.query.filter_by(task_id=service.task_id).count() == 2
        for item in expanded:
            series = task_kline_snapshot_repository.get_series_by_id(
                item["kline_series_id"]
            )
            source = task_kline_snapshot_repository.get_source_by_id(
                series["source_id"]
            )
            assert series_map[item["kline_key"]] == (
                task_kline_snapshot_service.merge_rows(source, series)
            )

        changed_rows = [dict(row, high=20.0, low=1.0) for row in _rows()]
        expanded_again, series_map_again = service._expand_random_price_groups(
            combinations,
            {"2026-2025": changed_rows},
            "random_price",
            "high_low",
            2,
            snapshot_meta=snapshot_meta,
        )

        assert [item["kline_series_id"] for item in expanded_again] == [
            item["kline_series_id"] for item in expanded
        ]
        assert series_map_again == series_map
        assert TaskKlineSource.query.filter_by(task_id=service.task_id).count() == 1
        assert TaskRandomSeries.query.filter_by(task_id=service.task_id).count() == 2


def test_persisted_values_match_legacy_memory_generation(app_factory):
    with app_factory.app_context():
        service = object.__new__(C7Service)
        service.task_id = "task-parity"
        combinations = [{
            "stock_code": "600000",
            "A1": 1,
            "B1": 2,
            "kline_key": "2026-2025",
        }]
        kline_map = {"2026-2025": _rows()}
        snapshot_meta = {
            "stock_name": "测试股票",
            "market_type": "cn",
            "data_source": "dfcf",
            "adjust_type": "forward",
        }

        _expanded, series_map = service._expand_random_price_groups(
            combinations,
            kline_map,
            "random_price",
            "high_low",
            1,
            snapshot_meta=snapshot_meta,
        )

        seed = "task-parity:600000:2026-2025:high_low:1"
        expected = KlineService.build_price_rows(
            _rows(),
            "random_price",
            include_ohlc=True,
            random_price_range="high_low",
            random_generator=random.Random(seed),
        )
        actual = series_map["2026-2025:random-1"]
        assert [row["stock_val"] for row in actual] == [
            row["stock_val"] for row in expected
        ]


def test_source_snapshot_preserves_vwap(app_factory):
    with app_factory.app_context():
        rows = _rows()
        for row in rows:
            row["vwap"] = 11.0
        source = _get_or_create_source(rows=rows)
        series = _get_or_create_series(source, rows=rows)

        merged = task_kline_snapshot_service.merge_rows(source, series)

        assert len(merged) == 31
        assert all(row["vwap"] == 11.0 for row in merged)
        assert all(row["close"] == 12.0 for row in merged)


def test_source_snapshot_without_vwap_keeps_none(app_factory):
    with app_factory.app_context():
        source = _get_or_create_source()
        series = _get_or_create_series(source)

        merged = task_kline_snapshot_service.merge_rows(source, series)

        assert all(row["vwap"] is None for row in merged)


def test_c1_1_custom_random_groups_persist_snapshot(app_factory):
    with app_factory.app_context():
        task = _create_task(task_id="task-c1_1-custom")
        rows = _rows()
        for row in rows:
            row["vwap"] = 11.0
            # custom 源来自 Sheet 现有K线，不携带外部数据源标记
            row.pop("data_source", None)
        service = object.__new__(C1_1Service)
        service.task_id = task.id
        service.config = {"market_type": "cn", "stock_name": "测试股票"}
        service._random_price_range = "high_low"
        service._random_group_count = 2
        service._dedupe_label = "C1_1"
        service._log_info = lambda *_args, **_kwargs: None

        data, _column_a_length, kline_map = service._get_custom_parameters(
            "600000", [["600000"]], {"custom": rows}
        )

        assert len(data) == 2
        assert all(item["kline_series_id"] for item in data)
        assert TaskKlineSource.query.filter_by(
            task_id=task.id, stock_code="600000", kline_key="custom"
        ).count() == 1
        assert TaskRandomSeries.query.filter_by(task_id=task.id).count() == 2
        source = task_kline_snapshot_repository.get_source(task.id, "600000", "custom")
        assert source["data_source"] == "custom"
        merged = task_kline_snapshot_service.merge_rows(
            source,
            task_kline_snapshot_repository.get_series_by_id(
                data[0]["kline_series_id"]
            ),
        )
        assert kline_map["custom:random-1"] == merged
        assert all(row["vwap"] == 11.0 for row in merged)


def test_c1_1_clear_input_columns_covers_all_columns(app_factory):
    """vwap 选填不影响清空语义：C1_1 清空必须覆盖 date..ext 全部七列（含 vwap/ext）。"""
    with app_factory.app_context():
        service = object.__new__(C1_1Service)
        service._log_info = lambda *_args, **_kwargs: None
        clears = []
        sheet = SimpleNamespace(
            title="C1_1",
            spreadsheet_id="sheet-1",
            get_last_row=lambda _column: 30,
            clear_range=lambda rng: clears.append(rng),
        )
        service.google_sheets = [sheet]

        service._clear_input_columns(sheet, {"_config_data": {}})

        assert clears == ["AA2:AG30"]


def test_save_task_result_writes_kline_series_link(app_factory):
    with app_factory.app_context():
        task = _create_task()
        source = _get_or_create_source(task_id=task.id)
        series = _get_or_create_series(source, task_id=task.id)

        service = object.__new__(C7Service)
        service.task_id = task.id
        service.task = None
        service.config = {}
        service.task_name = ""
        service.app = None
        service._log_error = lambda *_args, **_kwargs: None

        service._save_task_result(
            0,
            {"stock_code": "600000", "kline_series_id": series["id"]},
            {"sheet__title": {"D2": "1"}},
            True,
        )

        result = task_result_repository.list_by_task(task.id)[0]
        link = TaskResultKlineLink.query.filter_by(result_id=result["id"]).one()
        assert link.series_id == series["id"]
        assert link.task_id == task.id
        assert result["parameters"]["kline_series_id"] == series["id"]
        detail = task_result_repository.get_with_task_type(result["id"])
        assert detail["kline_series_id"] == series["id"]


def test_delete_result_removes_kline_link(app_factory):
    with app_factory.app_context():
        _create_task()
        source = _get_or_create_source()
        series = _get_or_create_series(source)
        result = _create_result(series_id=series["id"])

        assert task_result_repository.delete(result["id"]) is True

        assert TaskResult.query.filter_by(id=result["id"]).count() == 0
        assert TaskResultKlineLink.query.filter_by(result_id=result["id"]).count() == 0


def test_delete_task_result_dependencies_removes_links(app_factory):
    with app_factory.app_context():
        _create_task()
        source = _get_or_create_source()
        series = _get_or_create_series(source)
        first = _create_result(series_id=series["id"], step_index=0)
        second = _create_result(series_id=series["id"], step_index=1)

        delete_task_result_dependencies([first["id"]])
        db.session.commit()

        assert TaskResultKlineLink.query.filter_by(result_id=first["id"]).count() == 0
        assert TaskResultKlineLink.query.filter_by(result_id=second["id"]).count() == 1


def test_list_task_snapshots_does_not_select_blob_columns(app_factory):
    """列表只投影元数据：values_json 与源表数组列不得进入 SELECT。"""
    with app_factory.app_context():
        task = _create_task(task_id="task-list-projection")
        source = _get_or_create_source(task_id=task.id)
        _get_or_create_series(source, task_id=task.id)
        db.session.expire_all()

        statements = []

        def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            data = task_kline_snapshot_service.list_task_snapshots(task.id)
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)

        assert data["total"] == 1
        assert len(data["items"]) == 1
        lowered = [statement.lower() for statement in statements]
        assert any("t_param_task_random_series" in statement for statement in lowered)
        assert all("values_json" not in statement for statement in lowered)
        assert all("dates_json" not in statement for statement in lowered)


def test_export_csv_includes_vwap_when_present(app_factory):
    with app_factory.app_context():
        _create_task(task_id="task-csv-vwap")
        rows = _rows()
        for row in rows:
            row["vwap"] = 11.5
        source = _get_or_create_source(
            task_id="task-csv-vwap", kline_key="2026-vwap", rows=rows
        )
        series = _get_or_create_series(
            source,
            task_id="task-csv-vwap",
            kline_key="2026-vwap",
            rows=rows,
        )

        _filename, text = task_kline_snapshot_service.export_csv(
            task_kline_snapshot_service.get_series_detail(series["id"])
        )

        lines = text.splitlines()
        assert lines[0] == "stock_date,stock_val,open,high,low,close,vwap"
        assert lines[1].endswith(",11.5")


def test_list_series_results_returns_linked_results(app_factory):
    with app_factory.app_context():
        task = _create_task(task_id="task-series-results")
        source = _get_or_create_source(task_id=task.id)
        series = _get_or_create_series(source, task_id=task.id)
        result = _create_result(task_id=task.id, series_id=series["id"])

        data = task_kline_snapshot_service.list_series_results(
            series["id"], task_id=task.id
        )
        items = data["items"]

        assert data["total"] == 1
        assert [item["id"] for item in items] == [result["id"]]
        assert items[0]["step_index"] == 0
        assert items[0]["success"] is True


def test_list_series_results_paginates(app_factory):
    with app_factory.app_context():
        task = _create_task(task_id="task-series-results-page")
        source = _get_or_create_source(task_id=task.id)
        series = _get_or_create_series(source, task_id=task.id)
        results = [
            _create_result(
                task_id=task.id, series_id=series["id"], step_index=step
            )
            for step in range(3)
        ]

        data = task_kline_snapshot_service.list_series_results(
            series["id"], task_id=task.id, page=2, per_page=2
        )

        assert data["total"] == 3
        assert [item["id"] for item in data["items"]] == [results[2]["id"]]


def test_source_reuse_rejects_config_changes(app_factory):
    with app_factory.app_context():
        _get_or_create_source()

        cases = [
            ({"adjust_type": "none"}, "复权类型"),
            (
                {
                    "rows": [
                        dict(row, data_source="akshare")
                        for row in _rows()
                    ]
                },
                "数据源",
            ),
            (
                {
                    "rows": [
                        dict(row, stock_date=(
                            date(2026, 1, 2) + timedelta(days=offset)
                        ).isoformat())
                        for offset, row in enumerate(_rows())
                    ]
                },
                "K线窗口",
            ),
            (
                {
                    "rows": [
                        dict(row, vwap=11.0)
                        for row in _rows()
                    ]
                },
                "vwap",
            ),
        ]

        for overrides, field_label in cases:
            params = {
                "task_id": "task-snapshot",
                "stock_code": "600000",
                "stock_name": "测试股票",
                "market_type": "cn",
                "kline_key": "2026-2025",
                "data_source": "dfcf",
                "adjust_type": "forward",
                "rows": _rows(),
            }
            params.update(overrides)
            try:
                task_kline_snapshot_service.get_or_create_source(**params)
            except ValueError as exc:
                assert field_label in str(exc), (field_label, str(exc))
            else:
                raise AssertionError(f"{field_label} 未触发快照配置不一致")

        with pytest.raises(ValueError, match="全量重启"):
            task_kline_snapshot_service.get_or_create_source(
                task_id="task-snapshot",
                stock_code="600000",
                market_type="cn",
                kline_key="2026-2025",
                data_source="dfcf",
                adjust_type="none",
                rows=_rows(),
            )


def test_series_reuse_rejects_config_changes(app_factory):
    with app_factory.app_context():
        source = _get_or_create_source()
        _get_or_create_series(source)

        with pytest.raises(ValueError, match="随机种子"):
            task_kline_snapshot_service.get_or_create_series(
                source=source,
                task_id="task-snapshot",
                stock_code="600000",
                kline_key="2026-2025",
                random_group=1,
                price_mode="random_price",
                random_price_range="high_low",
                seed="different-seed",
                rows=_rows(),
            )

        other_source = _get_or_create_source(stock_code="000001")
        series_row = TaskRandomSeries.query.filter_by(
            task_id="task-snapshot",
            stock_code="600000",
            kline_key="2026-2025",
            random_group=1,
        ).one()
        series_row.source_id = other_source["id"]
        db.session.commit()

        with pytest.raises(ValueError, match="源快照"):
            task_kline_snapshot_service.get_or_create_series(
                source=source,
                task_id="task-snapshot",
                stock_code="600000",
                kline_key="2026-2025",
                random_group=1,
                price_mode="random_price",
                random_price_range="high_low",
                seed="task-snapshot:600000:2026-2025:high_low:1",
                rows=_rows(),
            )


def test_snapshot_mismatch_is_not_network_retryable():
    from app.utils.task_error_utils import is_retryable_network_error

    assert not is_retryable_network_error(
        ValueError("随机K线源快照与当前任务配置不一致，请对任务执行全量重启")
    )


def test_list_task_snapshots_filters_by_stock_and_group(app_factory):
    with app_factory.app_context():
        task = _create_task(task_id="task-filter")
        source_a = _get_or_create_source(task_id=task.id)
        source_b = _get_or_create_source(
            task_id=task.id, stock_code="000001"
        )
        _get_or_create_series(source_a, task_id=task.id, random_group=1)
        _get_or_create_series(source_a, task_id=task.id, random_group=2)
        _get_or_create_series(
            source_b,
            task_id=task.id,
            stock_code="000001",
            random_group=1,
        )

        by_stock = task_kline_snapshot_service.list_task_snapshots(
            task.id, stock_code="600000"
        )
        assert by_stock["total"] == 2
        assert {item["stock_code"] for item in by_stock["items"]} == {"600000"}

        by_group = task_kline_snapshot_service.list_task_snapshots(
            task.id, random_group=2
        )
        assert by_group["total"] == 1
        assert by_group["items"][0]["random_group"] == 2

        combined = task_kline_snapshot_service.list_task_snapshots(
            task.id, stock_code="600000", random_group=1
        )
        assert combined["total"] == 1
        assert combined["items"][0]["stock_code"] == "600000"
        assert combined["items"][0]["random_group"] == 1

        empty = task_kline_snapshot_service.list_task_snapshots(
            task.id, stock_code="999999"
        )
        assert empty["total"] == 0
        assert empty["items"] == []


def test_export_task_csv_streams_all_groups(app_factory):
    with app_factory.app_context():
        task = _create_task(task_id="task-export-all")
        rows = _rows()
        for row in rows:
            row["vwap"] = 11.5
        source = _get_or_create_source(
            task_id=task.id, kline_key="2026-export", rows=rows
        )
        for group in (1, 2):
            _get_or_create_series(
                source,
                task_id=task.id,
                kline_key="2026-export",
                random_group=group,
                rows=rows,
            )

        filename, chunks = task_kline_snapshot_service.export_task_csv(task.id)
        text = "".join(chunks)

        assert filename == "task-task-export-all-kline-snapshots.csv"
        assert text.startswith("\ufeff")
        lines = text.lstrip("\ufeff").splitlines()
        assert lines[0] == (
            "stock_code,stock_name,market_type,kline_key,dataset_key,"
            "random_group,random_price_range,stock_date,stock_val,"
            "open,high,low,close,vwap"
        )
        assert len(lines) == 1 + 2 * 31
        assert {line.split(",")[5] for line in lines[1:]} == {"1", "2"}
        assert all(line.endswith(",11.5") for line in lines[1:])
