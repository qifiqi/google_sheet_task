"""C6(3/3) 回归测试：多品校验类 ValueError 改抛 ValidationError 后，
calculate-ratios 等预览端点对非法比例输入保持 400 + 有意义文案
（修复审查发现的 P1 回归：裸 ValueError 曾落入全局兜底变 500）。
"""
import json
from datetime import datetime

import pytest

from app.exceptions import ValidationError
from app.extensions import db
from app.models import Task
from app.services.backtest_multi_product_service import (
    normalize_multi_product_config,
    parse_ratio,
)


def _make_bmp_task(task_id="bmp-preview-task"):
    task = Task(
        id=task_id,
        name=task_id,
        description="",
        task_type="backtest_multi_product",
        status="completed",
        config=json.dumps({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [
                {"stock_code": "600000", "ratio": "60", "parameters": [["1"]]},
                {"stock_code": "000001", "ratio": "40", "parameters": [["1"]]},
            ],
        }, ensure_ascii=False),
        created_at=datetime.now(),
    )
    db.session.add(task)
    db.session.commit()
    return task


def test_parse_ratio_rejects_invalid_as_validation_error():
    with pytest.raises(ValidationError, match="产品比例不是有效数字"):
        parse_ratio("abc")
    with pytest.raises(ValidationError, match="产品比例不能小于 0"):
        parse_ratio("-5")


def test_normalize_multi_product_config_rejects_bad_dates_as_validation_error():
    with pytest.raises(ValidationError, match="请填写有效的 K 线开始日期"):
        normalize_multi_product_config({
            "start_date": "bad-date",
            "end_date": "2024-12-31",
            "products": [{"stock_code": "600000"}, {"stock_code": "000001"}],
        })


def test_normalize_multi_product_config_rejects_single_product():
    with pytest.raises(ValidationError, match="至少需要 2 个产品"):
        normalize_multi_product_config({
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "products": [{"stock_code": "600000"}],
        })


def test_calculate_ratios_with_bad_ratio_returns_400(app_factory):
    """P1 回归守卫：非法比例在 calculate-ratios 端点保持 400 + 用户文案，
    不得落入全局兜底变 500。"""
    app = app_factory
    with app.app_context():
        _make_bmp_task("bmp-ratio-task")

    client = app.test_client()
    with app.app_context():
        from app.utils.auth import create_access_token
        from app.models import User
        from werkzeug.security import generate_password_hash

        user = User(username="ratio-user", password_hash="x", is_active=True)
        db.session.add(user)
        db.session.commit()
        token = create_access_token(user.id)

    resp = client.post(
        "/backtest-multi-product/api/global-preview/bmp-ratio-task/calculate-ratios",
        headers={"Authorization": f"Bearer {token}"},
        json={"ratios": [{"ratio": "not-a-number"}]},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["status"] == "error"
    assert body["message"], "必须返回有意义的用户文案"
