import json

from app.extensions import db
from app.models import StockMetadata, Task
from app.services.stock_metadata_service import upsert_stock_metadata
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
