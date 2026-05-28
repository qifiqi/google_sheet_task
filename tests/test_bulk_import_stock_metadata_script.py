import csv
import json
from pathlib import Path

from app.extensions import db
from app.models import StockMetadata
from scripts import bulk_import_stock_metadata as bulk_import_script


def test_bulk_import_stock_metadata_strips_table_prefix_columns(app_factory, tmp_path):
    app = app_factory
    csv_path = tmp_path / "stocks.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "task_result_summary_index.stock_code",
                "task_result_summary_index.stock_name",
                "task_result_summary_index.market_type",
                "task_result_summary_index.exchange_market",
                "task_result_summary_index.security_type_name",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "task_result_summary_index.stock_code": "600519",
                "task_result_summary_index.stock_name": "贵州茅台",
                "task_result_summary_index.market_type": "cn",
                "task_result_summary_index.exchange_market": "1",
                "task_result_summary_index.security_type_name": "A股",
            }
        )

    from scripts.bulk_import_stock_metadata import import_stock_metadata_file

    with app.app_context():
        result = import_stock_metadata_file(csv_path)
        item = StockMetadata.query.filter_by(stock_code="600519", market_type="cn").one()

    assert result["imported"] == 1
    assert item.stock_name == "贵州茅台"
    assert item.exchange_market == "1"


def test_bulk_import_stock_metadata_supports_json_rows(app_factory, tmp_path):
    app = app_factory
    json_path = tmp_path / "stocks.json"
    json_path.write_text(
        json.dumps(
            [
                {
                    "task_result_summary_index.stock_code": "AAPL",
                    "task_result_summary_index.stock_name": "Apple Inc.",
                    "task_result_summary_index.market_type": "us",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from scripts.bulk_import_stock_metadata import import_stock_metadata_file

    with app.app_context():
        result = import_stock_metadata_file(json_path)
        item = StockMetadata.query.filter_by(stock_code="AAPL", market_type="us").one()

    assert result["imported"] == 1
    assert item.stock_name == "Apple Inc."


def test_bulk_import_stock_metadata_resolves_stock_codes_only_and_deduplicates(app_factory, tmp_path, monkeypatch):
    app = app_factory
    text_path = tmp_path / "stock_codes.txt"
    text_path.write_text("600519\n600519\nAAPL\n", encoding="utf-8")

    calls: list[str] = []

    class FakeApi:
        def get_search_list_by_stock_code(self, stock, page_size=10):
            calls.append(stock)
            mapping = {
                "600519": [{
                    "source": "codetable",
                    "code": "600519",
                    "shortName": "贵州茅台",
                    "securityTypeName": "A股",
                    "market": "1",
                    "status": 10,
                    "marketType": "cn",
                    "isExactMatch": True,
                }],
                "AAPL": [{
                    "source": "suggest",
                    "code": "AAPL",
                    "shortName": "Apple Inc.",
                    "securityTypeName": "美股",
                    "market": "105",
                    "status": 10,
                    "marketType": "us",
                    "isExactMatch": True,
                }],
            }
            return mapping.get(str(stock).upper(), [])

    monkeypatch.setattr(bulk_import_script, "DFCJStockApi", FakeApi)

    with app.app_context():
        result = bulk_import_script.import_stock_metadata_file(text_path)
        cn_item = StockMetadata.query.filter_by(stock_code="600519", market_type="cn").one()
        us_item = StockMetadata.query.filter_by(stock_code="AAPL", market_type="us").one()

    assert result["imported"] == 2
    assert result["resolved"] == 2
    assert calls == ["600519", "AAPL"]
    assert cn_item.stock_name == "贵州茅台"
    assert us_item.stock_name == "Apple Inc."
