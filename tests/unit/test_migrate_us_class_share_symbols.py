from datetime import datetime

from scripts.migrate_us_class_share_symbols import apply_changes, build_migration_plan


def _row(row_id, stock_code, *, market_type="us", updated_at="2026-01-01T00:00:00+08:00", **extra):
    row = {
        "id": row_id,
        "stock_code": stock_code,
        "stock_name": "",
        "market_type": market_type,
        "exchange_market": None,
        "security_type_name": None,
        "source": None,
        "updated_at": updated_at,
    }
    row.update(extra)
    return row


def test_legacy_underscore_symbol_plans_single_code_update():
    plan = build_migration_plan([_row(1, "BRK_B", exchange_market="106")])

    assert len(plan) == 1
    assert plan[0]["survivor_id"] == 1
    assert plan[0]["delete_ids"] == []
    assert plan[0]["updates"]["stock_code"] == "BRK-B.US"


def test_canonical_symbol_without_duplicates_is_unchanged():
    assert build_migration_plan([_row(1, "BRK-B.US")]) == []


def test_duplicate_rows_merge_into_existing_canonical_row():
    plan = build_migration_plan([
        _row(1, "BRK_B", updated_at="2026-02-01T00:00:00+08:00", exchange_market="106"),
        _row(2, "BRK-B.US", updated_at="2026-01-01T00:00:00+08:00", stock_name="伯克希尔哈撒韦-B"),
    ])

    assert len(plan) == 1
    assert plan[0]["survivor_id"] == 2
    assert plan[0]["delete_ids"] == [1]
    assert plan[0]["updates"]["stock_code"] == "BRK-B.US"
    # Survivor 原先缺失的交易所编码从待删除行补齐。
    assert plan[0]["updates"]["exchange_market"] == "106"
    assert plan[0]["updates"]["stock_name"] == "伯克希尔哈撒韦-B"


def test_duplicate_legacy_rows_keep_latest_and_merge_missing_fields():
    plan = build_migration_plan([
        _row(1, "BRK_B", updated_at="2026-01-01T00:00:00+08:00", exchange_market="106"),
        _row(2, "BRK.B.US", updated_at="2026-02-01T00:00:00+08:00", stock_name="伯克希尔哈撒韦-B"),
    ])

    assert len(plan) == 1
    assert plan[0]["survivor_id"] == 2
    assert plan[0]["delete_ids"] == [1]
    assert plan[0]["updates"]["stock_code"] == "BRK-B.US"
    assert plan[0]["updates"]["exchange_market"] == "106"


def test_apply_merges_duplicate_rows_and_writes_backup(app_factory, tmp_path):
    from app.extensions import db
    from app.models import StockMetadata

    now = datetime.now()
    db.session.execute(StockMetadata.__table__.insert(), [
        {
            "stock_code": "BRK_B", "stock_name": "伯克希尔哈撒韦-B",
            "market_type": "us", "exchange_market": "106",
            "created_at": now, "updated_at": now,
        },
        {
            "stock_code": "BRK-B.US", "stock_name": "",
            "market_type": "us", "exchange_market": None,
            "created_at": now, "updated_at": now,
        },
    ])
    db.session.commit()
    rows = [
        row.to_dict()
        for row in StockMetadata.query.filter_by(market_type="us").order_by(StockMetadata.id).all()
    ]
    plan = build_migration_plan(rows)
    backup = tmp_path / "backup.json"

    apply_changes(db.session, plan, backup)

    db.session.expire_all()
    remaining = StockMetadata.query.filter_by(market_type="us").all()
    assert [row.stock_code for row in remaining] == ["BRK-B.US"]
    assert remaining[0].stock_name == "伯克希尔哈撒韦-B"
    assert remaining[0].exchange_market == "106"
    assert backup.exists()
