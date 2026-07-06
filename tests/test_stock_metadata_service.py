import json
from datetime import date, timedelta

from app.extensions import db
from app.models import StockMetadata, Task
from app.services.google_sheet_service_C4 import GoogleSheetService as C4GoogleSheetService
from app.services.stock_metadata_service import upsert_stock_metadata, upsert_stock_metadata_in_session
from app.services.task.facade import TaskManager


def test_upsert_stock_metadata_normalizes_search_result(app_factory):
    app = app_factory
    with app.app_context():
        upsert_stock_metadata({
            "code": "600519",
            "name": "贵州茅台",
            "market_type": "cn",
            "market": "1",
            "security_type_name": "A股",
            "source": "test",
        })

        item = StockMetadata.query.filter_by(stock_code="600519", market_type="cn").one()
        assert item.stock_name == "贵州茅台"
        assert item.exchange_market == "1"


def test_create_task_hydrates_stock_name_from_metadata(app_factory, monkeypatch):
    app = app_factory
    with app.app_context():
        db.session.add(StockMetadata(stock_code="600519", stock_name="贵州茅台", market_type="cn"))
        db.session.commit()
        manager = TaskManager()
        monkeypatch.setattr(manager, "validate_google_sheet_available_for_task", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(manager, "ensure_google_sheet_occupancy", lambda *_args, **_kwargs: None)

        task_id = manager.create_task(
            "task",
            "",
            "google_sheet_C5",
            {"stock_code": "600519", "market_type": "cn", "parameters": []},
        )

        task = db.session.get(Task, task_id)
        config = json.loads(task.config)
        assert config["stock_name"] == "贵州茅台"


def test_upsert_stock_metadata_reuses_pending_record_before_autoflush(app_factory):
    app = app_factory
    with app.app_context():
        first = upsert_stock_metadata_in_session({
            "code": "688188",
            "name": "柏楚电子",
            "market_type": "cn",
            "market": "1",
            "source": "first",
        })
        second = upsert_stock_metadata_in_session({
            "code": "688188",
            "name": "柏楚电子",
            "market_type": "cn",
            "market": "1",
            "source": "second",
        })
        db.session.commit()

        assert first.id == second.id
        item = StockMetadata.query.filter_by(stock_code="688188", market_type="cn").one()
        assert item.stock_name == "柏楚电子"
        assert item.source == "second"


def test_c4_parameter_generation_persists_stock_name_from_search(app_factory, monkeypatch):
    class FakeDfcfApi:
        def get_search_list_by_stock_code(self, stock_code, page_size):
            return [
                {
                    "code": stock_code,
                    "shortName": "贵州茅台",
                    "securityTypeName": "A股",
                    "market": "1",
                    "source": "test",
                }
            ]

        def get_stock_kline_data(self, stock_code, market, limit, adjust_type=None):
            start = date(2024, 1, 1)
            return [
                {
                    "stock_date": (start + timedelta(days=index)).isoformat(),
                    "stock_kp": 100 + index,
                    "stock_sp": 100 + index,
                }
                for index in range(100)
            ]

    app = app_factory
    monkeypatch.setattr("app.services.google_sheet_service_C4.DFCJStockApi", FakeDfcfApi)
    with app.app_context():
        combinations, _column_a_length = C4GoogleSheetService._get_all_parameters(
            "600519",
            "single",
            "2024-03-31",
            "2024-01-01",
            "cn",
            [],
        )

        assert combinations[0]["stock_name"] == "贵州茅台"
        item = StockMetadata.query.filter_by(stock_code="600519", market_type="cn").one()
        assert item.stock_name == "贵州茅台"
