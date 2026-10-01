"""analyze 接口 include_series 净值序列导出（V3 图表数据源）。

缺省不带 series 键（老调用方零影响）；显式 include_series=true 时
data.series 携带 dates/index_nav/start_nav/excess_nav，dual 模式三帧同轴，
single 模式（无基准）series 为 null。
"""

from app.extensions import db
from app.models import Task, TaskResult, TaskResultReturn
from app.utils.return_series import build_return_series_fields


_DUAL_ROWS = [
    {"date": "2024-01-01", "index_return": 0.01, "start_return": 0.02},
    {"date": "2024-01-02", "index_return": 0.02, "start_return": 0.03},
    {"date": "2024-01-03", "index_return": -0.01, "start_return": 0.01},
]


def _user_headers(app, monkeypatch, username="series-user"):
    # 单 Token 模式：本地登录/JWT 已退役；AUTH_ENABLED=false 下以 mock 用户
    # 验证 series 契约（username 仅用于用例间日志区分）。
    monkeypatch.setenv("AUTH_ENABLED", "false")
    return {"Accept": "*/*"}


def _seed_result_with_returns(app, task_id="series-nav-task"):
    """构造带收益序列的成功结果，返回 result_id。"""
    with app.app_context():
        task = Task(id=task_id, name="序列导出任务", task_type="backtest_training", status="completed", config="{}")
        series = TaskResultReturn(
            task_id=task.id,
            **build_return_series_fields(_DUAL_ROWS, stock_code="600519", stock_name="贵州茅台"),
        )
        db.session.add_all([task, series])
        db.session.flush()
        result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters='{"stock_code":"600519","stock_name":"贵州茅台"}',
            result="{}",
            return_series_id=series.id,
            success=True,
        )
        db.session.add(result)
        db.session.commit()
        return result.id


def test_analyze_include_series_returns_nav_series(app_factory, monkeypatch):
    app = app_factory
    text = "\n".join(f"{row['date']}\t{row['index_return']}\t{row['start_return']}" for row in _DUAL_ROWS)
    headers = _user_headers(app, monkeypatch, username="series-dual-user")

    body = app.test_client().post(
        '/api/performance-analysis/analyze',
        headers=headers,
        json={"data": text, "include_series": True},
    ).get_json()

    assert body["status"] == "success"
    series = body["data"]["series"]
    assert series is not None
    assert series["dates"] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert len(series["index_nav"]) == len(series["start_nav"]) == len(series["excess_nav"]) == 3
    # 净值首点 = 1 + 首期收益（1 点初值口径，与 metrics 净值列一致）
    assert series["index_nav"][0] == 1.01
    assert series["start_nav"][0] == 1.02
    assert series["excess_nav"][0] == 1.01


def test_analyze_without_include_series_omits_series(app_factory, monkeypatch):
    app = app_factory
    text = "\n".join(f"{row['date']}\t{row['index_return']}\t{row['start_return']}" for row in _DUAL_ROWS)
    headers = _user_headers(app, monkeypatch, username="series-omit-user")

    body = app.test_client().post(
        '/api/performance-analysis/analyze',
        headers=headers,
        json={"data": text},
    ).get_json()

    assert body["status"] == "success"
    assert "series" not in body["data"]


def test_analyze_result_include_series(app_factory, monkeypatch):
    app = app_factory
    result_id = _seed_result_with_returns(app)
    headers = _user_headers(app, monkeypatch, username="series-result-user")

    body = app.test_client().post(
        '/api/performance-analysis/analyze',
        headers=headers,
        json={"result_id": result_id, "include_series": True},
    ).get_json()

    assert body["status"] == "success"
    series = body["data"]["series"]
    assert series["dates"] == [row["date"] for row in _DUAL_ROWS]
    assert all(value is not None for value in series["start_nav"])


def test_analyze_include_series_false_string_is_rejected_as_no_series(app_factory, monkeypatch):
    """include_series 经 coerce_bool 解析，"false"/"0" 等字面量不导出序列。"""
    app = app_factory
    text = "\n".join(f"{row['date']}\t{row['index_return']}\t{row['start_return']}" for row in _DUAL_ROWS)
    headers = _user_headers(app, monkeypatch, username="series-coerce-user")

    body = app.test_client().post(
        '/api/performance-analysis/analyze',
        headers=headers,
        json={"data": text, "include_series": "false"},
    ).get_json()

    assert body["status"] == "success"
    assert "series" not in body["data"]


def test_analyze_single_mode_include_series_returns_null_series(app_factory, monkeypatch):
    """单列收益（无基准）走 single 管线：无序列可导，series 置 null。"""
    app = app_factory
    text = "\n".join(["2024-01-01\t0.02", "2024-01-02\t0.03", "2024-01-03\t-0.01"])
    headers = _user_headers(app, monkeypatch, username="series-single-user")

    body = app.test_client().post(
        '/api/performance-analysis/analyze',
        headers=headers,
        json={"data": text, "include_series": True},
    ).get_json()

    assert body["status"] == "success"
    assert body["data"]["results"]["analysis_mode"] == "single"
    assert body["data"]["series"] is None
