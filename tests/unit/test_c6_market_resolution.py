"""市场代码统一解析与 stock_meta 前置查询测试（2026-09 K线市场代码修复）。

覆盖：
- resolve_market_type 统一接口：A 股场内数字（0/1，含 ETF/基金）→ cn；
- get_stock_market：ETF/基金前缀不再判为未知；
- resolve_stock：stock_meta 前置命中不调东财；未命中走东财并回写 stock_meta。
"""
import json
from datetime import datetime

import pytest

from app.extensions import db
from app.models import StockMetadata
from app.repositories import stock_metadata_repository
from app.services.stock_search_service import StockSearchService
from app.utils.market import resolve_market_type


class _DfcfApi:
    """东财桩：ETF 510300 返回 A 股场内 market=1。"""

    def get_search_list_by_stock_code(self, _keyword, _page_size):
        return [
            {"code": "510300", "shortName": "沪深300ETF", "market": "1", "status": 10},
            {"code": "159919", "shortName": "深300ETF", "market": "0", "status": 10},
        ]


# ---------------------------------------------------------------------------
# resolve_market_type 统一接口
# ---------------------------------------------------------------------------

def test_resolve_market_type_cn_exchange_numbers_cover_etf():
    """A 股场内数字（沪1/深0）一律归 cn，覆盖 ETF/基金等场内品种。"""
    assert resolve_market_type("1") == "cn"
    assert resolve_market_type("0") == "cn"


def test_resolve_market_type_known_markets_unchanged():
    assert resolve_market_type("105") == "en"
    assert resolve_market_type("116") == "hk"
    assert resolve_market_type("177") == "kr"


def test_resolve_market_type_futures_exchange_numbers():
    """期货交易所编号（中金所8/上期所113/大商所114/郑商所115/能源142/广期所225）归 futures。"""
    for number in ("8", "113", "114", "115", "142", "225"):
        assert resolve_market_type(number) == "futures", number


def test_search_stocks_keeps_futures_market_filter():
    """期货品种按 market 数字归入 futures 后，不再被 cn/en 过滤丢弃。"""
    service = StockSearchService(dfcf_api=type(
        "_DfcfApi",
        (),
        {"get_search_list_by_stock_code": staticmethod(lambda *a, **k: [
            {"code": "IF2501", "shortName": "沪深2501", "market": "8", "status": 10},
            {"code": "510300", "shortName": "沪深300ETF", "market": "1", "status": 10},
        ])},
    )())

    futures = service.search_stocks("IF", market_type="futures")
    assert [(item["code"], item["market_type"]) for item in futures] == [
        ("IF2501", "futures"),
    ]

    cn = service.search_stocks("IF", market_type="cn")
    assert [(item["code"], item["market_type"]) for item in cn] == [
        ("510300.SS", "cn"),
    ]


def test_resolve_market_type_unmapped_falls_to_security_type_name():
    assert resolve_market_type("999", "日本") == "jp"
    assert resolve_market_type("999") is None


# ---------------------------------------------------------------------------
# get_stock_market（内置K线库市场后缀）
# ---------------------------------------------------------------------------

def test_get_stock_market_covers_etf_prefixes():
    service = __import__("app.services.kline_service", fromlist=["KlineService"]).KlineService
    assert service.get_stock_market("510300") == "510300.SH"
    assert service.get_stock_market("159919") == "159919.SZ"
    assert service.get_stock_market(600000) == "600000.SH"
    assert service.get_stock_market("000001") == "000001.SZ"


# ---------------------------------------------------------------------------
# resolve_stock：stock_meta 前置查询
# ---------------------------------------------------------------------------

def test_resolve_stock_hits_stock_meta_without_dfcf(app_factory, monkeypatch):
    """此前成功解析过的代码经 stock_meta 直接命中，不再调用东财搜索。"""
    app = app_factory
    with app.app_context():
        task = _make_bmp_task(app)
        # 预置 stock_meta：东财交易所编号 1（沪）
        stock_metadata_repository.upsert({
            "stock_code": "510300.SS",
            "stock_name": "沪深300ETF",
            "market_type": "cn",
            "exchange_market": "1",
            "security_type_name": "基金",
            "source": "codetable",
        }, commit=False)

        dfcf_calls = []
        service = StockSearchService(dfcf_api=type(
            "Spy",
            (),
            {"get_search_list_by_stock_code": staticmethod(
                lambda *a, **k: dfcf_calls.append(a) or []
            )},
        )())
        monkeypatch.setattr(service, "save_metadata", lambda _rows: None)

        resolved = service.resolve_stock("510300", "cn")

        assert resolved["code"] == "510300.SS"
        assert resolved["exchange_market"] == "1"
        assert dfcf_calls == []
        assert task.id  # 保持 app_context 内任务存在性引用


def _make_bmp_task(app):
    from app.models import Task

    task = Task(
        id="meta-first-task",
        name="meta-first-task",
        description="",
        task_type="backtest_multi_product",
        status="completed",
        created_at=datetime.now(),
    )
    db.session.add(task)
    db.session.commit()
    return task


def test_resolve_stock_miss_falls_back_to_dfcf_and_persists(app_factory, monkeypatch):
    """stock_meta 未命中时走东财搜索，解析成功后回写 stock_meta（commit=False）。"""
    app = app_factory
    with app.app_context():
        _make_bmp_task(app)

        service = StockSearchService(dfcf_api=_DfcfApi())

        upserts = []
        monkeypatch.setattr(
            stock_metadata_repository,
            "upsert",
            lambda fields, commit=True: upserts.append((fields, commit)),
        )

        resolved = service.resolve_stock("510300", "cn")

        assert resolved["code"] == "510300.SS"
        assert resolved["exchange_market"] == "1"
        assert len(upserts) == 1
        assert upserts[0][1] is False  # commit=False 随任务事务提交

