import json
from datetime import datetime, timedelta

import pytest

from app.utils.return_series import parse_return_series_fields
from app.extensions import db
from app.models import BacktestProductResultCache, TaskResult, TaskResultReturn
from app.services.backtest_training_api_service import _get_summary_derived_value
from app.services.backtest_multi_product_service import (
    BacktestMultiProductService,
    normalize_multi_product_config,
)
from app.services.backtest_training_service import BacktestTrainingService
from app.services.xpl_service import XPLAnalyzer


def _kline_rows(start_date, end_date):
    current = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    rows = []
    while current <= end:
        rows.append({
            "stock_date": current.strftime("%Y-%m-%d"),
            "open": 9,
            "close": 10,
            "vwap": 12,
        })
        current += timedelta(days=1)
    return rows


def _product(index, *, parameters=None, is_fixed=False):
    return {
        "product_name": f"产品{index}",
        "stock_code": f"TEST{index}",
        "market_type": "cn",
        "ratio": "50",
        "is_fixed": is_fixed,
        "sheet": {"spreadsheet_id": f"sheet-{index}", "sheet_name": "data", "title": "C3"},
        "parameters": parameters or [["p1", "p2"]],
    }


class _RecordingKlineService:
    """记录 get_kline_data 调用并可选禁止证券解析的 KlineService 替身。"""

    def __init__(self, rows, allow_resolve=True):
        self.calls = []
        self._rows = rows

        class _Search:
            def __init__(self, allow):
                self._allow = allow

            def resolve_stock(self, *_args, **_kwargs):
                if not self._allow:
                    raise AssertionError("selected stock should not be searched again")

        self.stock_search_service = _Search(allow_resolve)

    def get_kline_data(self, stock_code, market_type, limit, **kwargs):
        self.calls.append((stock_code, market_type, limit, kwargs))
        return list(self._rows)

    def build_price_rows(self, klines, price_mode, **kwargs):
        from app.services.kline_service import KlineService

        return KlineService.build_price_rows(klines, price_mode, **kwargs)

def test_backtest_training_save_result_persists_return_series(app_factory):
    app = app_factory
    with app.app_context():
        service = BacktestTrainingService({}, "task-id", app=app)

        service._save_task_result(
            0,
            {"stock_code": "600000"},
            {"metric": 1},
            True,
            return_date=[
                {"date": "2024-01-01", "index_return": 0.1, "start_return": 0.2},
                {"date": "2024-01-02", "index_return": 0.3, "start_return": 0.4},
            ],
        )

        result = TaskResult.query.filter_by(task_id="task-id").one()
        series = db.session.get(TaskResultReturn, result.return_series_id)
        rows = parse_return_series_fields(series)

        assert result.success is True
        assert [row["date"] for row in rows] == ["2024-01-01", "2024-01-02"]
        assert [row["index_return"] for row in rows] == [0.1, 0.3]


def test_backtest_training_full_range_uses_configured_end_date(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(
        service, "kline_service",
        _RecordingKlineService(_kline_rows("2022-01-01", "2024-06-30")),
    )

    combinations, _column_length, kline_map = service._get_all_parameters(
        [2022, 2023, 2024],
        [],
        [["param-a"]],
        "600000",
        include_full_year_range=True,
        end_date="2024-06-30",
    )

    assert combinations == [{
        "parameter": ["param-a"],
        "stock_code": "600000",
        "year": "2022-2024",
        "Kline_key": "2022-2024",
    }]
    assert kline_map["2022-2024"][-1]["stock_date"] == "2024-06-30"


def test_multi_product_kline_limit_covers_interval_from_start_to_current_date(monkeypatch):
    class _FixedDateTime:
        strptime = staticmethod(datetime.strptime)

        @staticmethod
        def now():
            return datetime(2026, 9, 1)

    service = BacktestMultiProductService({}, "task-id")
    recorder = _RecordingKlineService(_kline_rows("2021-01-01", "2025-12-31"))
    service.kline_service = recorder
    monkeypatch.setattr("app.services.backtest_multi_product_service.datetime", _FixedDateTime)

    kline = service._get_kline_by_date_range(
        "SOXX.US",
        "en",
        "2021-01-01",
        "2025-12-31",
        price_mode="sp_price",
    )

    assert len(kline) > 100
    assert recorder.calls[0][2] == 1548


def test_backtest_training_short_listing_history_recent_years_is_allowed(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    monkeypatch.setattr(
        service, "kline_service",
        _RecordingKlineService(_kline_rows("2023-06-01", "2025-06-30")),
    )

    combinations, _column_length, kline_map = service._get_all_parameters(
        [],
        [5],
        [["param-a"]],
        "600000",
        end_date="2025-06-30",
    )

    assert combinations[0]["Kline_key"] == "2025-2020"
    assert kline_map["2025-2020"][0]["stock_date"] == "2023-06-01"


def test_backtest_training_vwap_uses_dfcf_for_en_market(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    service.YF_api.get_kline_data = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Yahoo should not be used for vwap_price")
    )
    search_calls = []
    service.dfcf_api.get_search_list_by_stock_code = lambda *args, **_kwargs: (
        search_calls.append(args[0]) or [{"code": "SOXX", "market": "105", "shortName": "半导体ETF-iShares"}]
    )
    service.dfcf_api.get_stock_kline_data = (
        lambda *_args, **_kwargs: _kline_rows("2023-01-01", "2024-02-15")
    )

    _combinations, _column_length, kline_map = service._get_all_parameters(
        [],
        [1],
        [["param-a"]],
        "SOXX",
        price_mode="vwap_price",
        market_type="en",
        end_date="2024-02-15",
    )

    assert kline_map["2024-2023"][0]["stock_val"] == 12
    assert search_calls == ["SOXX"]


def test_backtest_training_selected_cn_quote_skips_stock_search(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    fake_kline = _RecordingKlineService(
        _kline_rows("2023-01-01", "2024-02-15"), allow_resolve=False
    )
    monkeypatch.setattr(service, "kline_service", fake_kline)

    service._get_all_parameters(
        [],
        [1],
        [["param-a"]],
        "600000",
        exchange_market="1",
        end_date="2024-02-15",
    )

    code, market_type, _limit, kwargs = fake_kline.calls[0]
    assert (code, market_type) == ("600000", "cn")
    assert kwargs.get("exchange_market") == "1"


def test_backtest_training_selected_en_vwap_quote_skips_stock_search(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    fake_kline = _RecordingKlineService(
        _kline_rows("2023-01-01", "2024-02-15"), allow_resolve=False
    )
    monkeypatch.setattr(service, "kline_service", fake_kline)

    service._get_all_parameters(
        [],
        [1],
        [["param-a"]],
        "SOXX",
        market_type="en",
        price_mode="vwap_price",
        exchange_market="105",
        end_date="2024-02-15",
    )

    code, market_type, _limit, kwargs = fake_kline.calls[0]
    assert (code, market_type) == ("SOXX", "en")
    assert kwargs.get("exchange_market") == "105"


def test_backtest_sheet_config_supports_c7():
    config = {
        "sheet": {"title": "策略 C7 模型"},
        "c7_input_column_a": "A",
        "c7_input_column_b": "B",
        "c7_output_range_1": "D8:D26",
        "c7_output_range_2": "D28:F31",
        "c7_output_column_j": "J",
        "c7_output_column_l": "L",
        "c7_parameter_positions": ["A1", "B1"],
    }

    assert BacktestTrainingService._c3_to_c5_get_config(config) == (
        "A",
        "B",
        "D8:D26",
        "D28:F31",
        "J",
        "L",
        ["A1", "B1"],
        ["D8", "D9"],
        "A",
    )


def test_backtest_sheet_config_supports_c7_0_3():
    config = {
        "sheet": {"title": "C7.0.3 回测", "c7_model_version": "c7_0_3"},
    }

    assert BacktestTrainingService._c3_to_c5_get_config(config) == (
        "CC",
        "CG",
        "D2:D20",
        "D22:F25",
        "J",
        "L",
        ["A1", "B1"],
        ["D2", "D3"],
        "CC",
    )


def test_backtest_c7_0_3_uses_ohlc_and_close_for_index_returns(monkeypatch):
    service = BacktestTrainingService({}, "task-id")
    kline_rows = _kline_rows("2023-01-02", "2024-02-15")
    for row in kline_rows:
        row.update({"high": 11, "low": 8})
    next(row for row in kline_rows if row["stock_date"] == "2023-02-16")["close"] = 12
    monkeypatch.setattr(
        service, "kline_service", _RecordingKlineService(kline_rows)
    )

    _combinations, _column_length, kline_map = service._get_all_parameters(
        [], [1], [["2.3", "3"]], "600000", price_mode="ohlc_price",
        end_date="2024-02-15", include_ohlc=True,
    )

    kline = kline_map["2024-2023"]
    assert {"open", "high", "low", "close"}.issubset(kline[0])
    assert service._calculate_c7_0_3_index_returns(kline)[1] == pytest.approx(0.2)


def test_backtest_c7_0_3_execution_writes_ohlc_and_handles_first_div_zero(monkeypatch):
    class C7V03Sheet:
        spreadsheet_id = "c7-v03-single"
        title = "C7.0.3.v20260729-回测-sharable-manual"

        def __init__(self):
            self.clear_calls = []
            self.update_payloads = []
            self.result_reads = 0

        def clear_range(self, range_a1):
            self.clear_calls.append(range_a1)

        def update_jumped_cells(self, payload):
            self.update_payloads.append(dict(payload))

        def get_range(self, range_a1, value_render_option=None):
            assert range_a1 == "D2:D20"
            self.result_reads += 1
            return {"D2": "1" if self.result_reads > 1 else "0", "D3": "2"}

        def get_ranges(self, ranges):
            assert ranges == ["D22:F25", "L2:L3"]
            return {
                "D22:F25": {},
                "L2:L3": {"L2": "#DIV/0!", "L3": "20%"},
            }

    service = BacktestTrainingService({}, "task-id")
    sheet = C7V03Sheet()
    service.google_sheet = sheet
    service.xpl = type(
        "XPL",
        (), {
            "get_calculate_metrics_v1": lambda _self, rows: {"rows": rows},
            # 统一存储后，执行链路通过 V1 门面取 (metrics, 三条DataFrame) 结果。
            "_calculate_metrics_v1": lambda _self, rows, return_dataframes=False: (
                {"rows": rows}, None, None, None,
            ),
        },
    )()
    monkeypatch.setattr(service, "_interruptible_sleep", lambda _seconds: True)
    monkeypatch.setattr(service, "_get_execution_poll_delay_bounds", lambda: (0, 0))
    monkeypatch.setattr(service, "_get_execution_poll_delay", lambda *_args: 0)

    kline = [
        {"stock_date": "2025-01-01", "open": 9, "high": 11, "low": 8, "close": 10, "stock_val": 10},
        {"stock_date": "2025-01-02", "open": 10, "high": 12, "low": 9, "close": 11, "stock_val": 11},
    ]
    success, _result, return_date = service._execute_parameter_combination(
        10,
        {"parameter": ["2.3", "3"], "stock_code": "600000", "Kline_key": "2026-2025"},
        {"combination": {}},
        {"sheet": {"title": sheet.title, "c7_model_version": "c7_0_3"}},
        {"2026-2025": kline},
    )

    assert success is True
    assert sheet.clear_calls == ["CC2:CG12"]
    assert sheet.update_payloads[0]["CC2"] == "2025-01-01"
    assert sheet.update_payloads[0]["CD2"] == 9
    assert return_date[0]["start_return"] == 0
    assert return_date[1]["index_return"] == pytest.approx(0.1)


def test_xpl_reads_c7_0_3_ohlc_layout(monkeypatch):
    class C7V03Sheet:
        title = "C7.0.3.v20260729"

        def get_last_row(self, column):
            assert column == "CC"
            return 3

        def get_range_2d(self, range_a1, _render_option):
            values = {
                "CC2:CG3": [["2025-08-05", 9, 11, 8, 10], ["2025-08-06", 10, 12, 9, 11]],
                "L2:L3": [[0], [0.2]],
                "C2:D20": [["Return%", "20%"], ["Annualized", "20%"]],
            }
            return values[range_a1]

    analyzer = XPLAnalyzer()
    monkeypatch.setattr(analyzer, "_init_google_sheet", lambda *_args: C7V03Sheet())

    data, result, sheet_df = analyzer.get_google_sheet_data("sheet-id", "control")

    assert data[0]["index_return"] == 0
    assert data[1]["index_return"] == pytest.approx(0.1)
    assert data[1]["start_return"] == pytest.approx(0.2)
    assert result["Return%"] == "20%"
    assert list(sheet_df.columns) == ["date", "open", "high", "low", "close", "index_return", "start_return"]


def test_c7_summary_excess_return_uses_shifted_c5_cells():
    column = {
        "model_name": "C7",
        "raw_metrics": {
            "D8": "32.47%",
            "D11": "21.14%",
        },
    }

    assert _get_summary_derived_value(column, "excess_return") == "11.33%"


def test_c7_0_3_summary_uses_c5_result_cells():
    column = {
        "model_name": "C7",
        "c7_model_version": "c7_0_3",
        "raw_metrics": {
            "D2": "32.47%",
            "D5": "21.14%",
        },
    }

    assert _get_summary_derived_value(column, "excess_return") == "11.33%"


def test_c7_summary_formats_raw_drawdown_as_percentage_points():
    column = {
        "model_name": "C7",
        "raw_metrics": {"D10": "-0.88"},
    }

    assert _get_summary_derived_value(column, "max_drawdown") == "-88.00%"


def test_multi_product_normalize_rejects_parameter_count_mismatch():
    with pytest.raises(ValueError, match="参数行数必须一致"):
        normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [
                _product(1, parameters=[["a"], ["b"]]),
                _product(2, parameters=[["a"]]),
            ],
        })


def test_multi_product_fixed_cache_exists_and_gets_cached_payload(app_factory):
    app = app_factory
    with app.app_context():
        config = {
            "fixed_product_batch_id": "batch-1",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
        product = _product(1, parameters=[["p1", "p2"]], is_fixed=True)
        cache_key = BacktestMultiProductService._build_fixed_product_cache_key(
            config,
            product,
            ["p1", "p2"],
        )
        db.session.add(BacktestProductResultCache(
            batch_id="batch-1",
            cache_key=cache_key,
            result_json=json.dumps({"metric": 1}),
            returns_json=json.dumps({"dates": ["2024-01-01"]}),
            source_task_id="source",
            source_step_index=0,
        ))
        db.session.commit()

        service = BacktestMultiProductService({}, "task-id", app=app)

        assert BacktestMultiProductService.fixed_product_cache_exists(config, product) is True
        cached = service._get_fixed_product_cache(config, product, ["p1", "p2"])
        assert json.loads(cached["result_json"]) == {"metric": 1}
        assert cached["source_task_id"] == "source"
