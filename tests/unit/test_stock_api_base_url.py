# -*- coding: utf-8 -*-
"""STOCK_BASE_URL 统一解析：K线 SDK / StockAPIClient / SmartProxyManager 共用。"""

import pytest
from flask import Flask

from app.utils.db_stock_api import StockAPIClient
from app.utils.proxy_manager import SmartProxyManager
from app.utils.stock_api_base import resolve_stock_base_url

HISTORY_DEFAULT = 'http://stockapi.stplan.cn'


@pytest.fixture
def stock_app():
    app = Flask(__name__)
    app.config['STOCK_BASE_URL'] = 'http://stock-svc:8080'
    with app.app_context():
        yield app


def test_explicit_base_url_wins_over_config(stock_app):
    assert resolve_stock_base_url('http://explicit', fallback=HISTORY_DEFAULT) == 'http://explicit'


def test_config_value_used_when_no_explicit_param(stock_app):
    assert resolve_stock_base_url('', fallback=HISTORY_DEFAULT) == 'http://stock-svc:8080'


def test_fallback_without_app_context():
    # 无应用上下文（独立脚本/单测）时回退调用方历史默认地址。
    assert resolve_stock_base_url('', fallback=HISTORY_DEFAULT) == HISTORY_DEFAULT


def test_stock_api_client_resolves_base_url_from_config(stock_app):
    assert StockAPIClient().base_url == 'http://stock-svc:8080'
    assert SmartProxyManager().base_url == 'http://stock-svc:8080'


def test_clients_fall_back_to_history_default_without_config():
    assert StockAPIClient().base_url == HISTORY_DEFAULT
    assert SmartProxyManager().base_url == HISTORY_DEFAULT


def test_explicit_param_still_supported(stock_app):
    assert StockAPIClient(base_url='http://override/').base_url == 'http://override'
    assert SmartProxyManager(base_url='http://override/').base_url == 'http://override'


def test_proxy_endpoint_built_from_resolved_base_url(stock_app):
    manager = SmartProxyManager()
    assert manager.proxy_config['url'] == 'http://stock-svc:8080/api/StockDic/GetProxyListByOne'
