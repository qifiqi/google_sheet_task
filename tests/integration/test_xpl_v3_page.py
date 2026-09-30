"""V3 回测数据分析页：页面 DOM 契约 + analyze include_series 链路冒烟。

设计文档：docs/design/performance-analysis-v3/01-设计方案.md。
V3 是独立交付物（templates/performance_analysis/v3.html + pages/performance_analysis_v3.js），
V2 页与其 JS 保持零改动（除 adminResults.detail 端点修复）。
"""

from app.extensions import db
from app.models import Task, TaskResult, TaskResultReturn
from app.utils.return_series import build_return_series_fields


_DUAL_ROWS = [
    {"date": "2024-01-01", "index_return": 0.01, "start_return": 0.02},
    {"date": "2024-01-02", "index_return": 0.02, "start_return": 0.03},
    {"date": "2024-01-03", "index_return": -0.01, "start_return": 0.01},
]


def _cookie_client(app, username="xpl-v3-cookie-user"):
    from werkzeug.security import generate_password_hash

    from app.models import User
    from app.utils.auth import ACCESS_TOKEN_COOKIE, create_access_token

    with app.app_context():
        user = User(username=username, password_hash=generate_password_hash("pw"), is_active=True)
        db.session.add(user)
        db.session.commit()
        token = create_access_token(user.id)
    client = app.test_client()
    client.set_cookie(ACCESS_TOKEN_COOKIE, token)
    return client


def _user_headers(app, username="xpl-v3-api-user"):
    from werkzeug.security import generate_password_hash

    from app.models import User
    from app.utils.auth import create_access_token

    with app.app_context():
        user = User(username=username, password_hash=generate_password_hash("pw"), is_active=True)
        db.session.add(user)
        db.session.commit()
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_xpl_v3_page_exposes_sections_and_sources(app_factory):
    client = _cookie_client(app_factory)
    response = client.get('/performance-analysis/v3')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # 标题与四大来源 Tab
    assert 'V3：回测数据分析' in body
    for tab in ('Google Sheet', '粘贴数据', '导入 Excel', '结果分析', '参数配置'):
        assert tab in body
    # 分区骨架（锚点导航消费的 section id）
    for section in ('sec-kpi', 'sec-nav', 'sec-annual', 'sec-monthly', 'sec-dist', 'sec-extreme', 'sec-details'):
        assert f'id="{section}"' in body
    # 数据集栏（多数据对比接入口）与关键图表画布
    assert 'id="v3-dataset-bar"' in body
    for canvas in ('v3-chart-nav', 'v3-chart-underwater', 'v3-chart-excess-line', 'v3-chart-annual-returns', 'v3-chart-radar',
                   'v3-chart-rolling', 'v3-chart-scatter', 'v3-chart-dist-monthly', 'v3-chart-hist-daily', 'v3-chart-extreme'):
        assert f'id="{canvas}"' in body
    # 直方图头部有对称分箱说明位
    assert 'id="v3-hist-limit"' in body
    # 热力图容器 + 基准/策略/超额切换
    assert 'id="v3-heatmap"' in body
    assert 'id="v3-heatmap-switch"' in body
    # 八章明细 tab + Sheet 结果 + 全量指标 + JSON
    for tab in ('tab-ret', 'tab-risk', 'tab-ra', 'tab-monthly', 'tab-daily',
                'tab-excess', 'tab-extreme', 'tab-capital', 'tab-sheet', 'tab-allmetrics', 'tab-raw'):
        assert f'id="{tab}"' in body
    # 导出与 Word 弹窗
    assert 'id="btn-export-v3"' in body
    assert 'id="btn-export-word"' in body
    assert 'id="word-export-options-modal"' in body
    # 脚本引用：v3 专属 JS/CSS + 统一词表 + 本地 Chart.js（不走 CDN）
    assert '/static/js/pages/performance_analysis_v3.js' in body
    assert '/static/css/pages/performance_analysis_v3.css' in body
    assert '/static/js/common/metric-names.js' in body
    assert '/static/js/chart.umd.min.js' in body
    assert 'performance_analysis_v2.js' not in body
    assert 'cdn.jsdelivr.net/npm/chart.js' not in body


def test_xpl_v3_page_js_uses_registry_and_metric_names():
    """页面 JS 经 DatasetStore 登记数据集、经词表取名、经 api.js 出接口。"""
    with open('static/js/pages/performance_analysis_v3.js', encoding='utf-8') as f:
        page_js = f.read()
    assert 'function addDataset' in page_js
    assert 'function compareDatasets' in page_js
    assert 'include_series: true' in page_js
    assert 'Api.endpoints.performanceAnalysis.analyze' in page_js
    assert 'Api.endpoints.task.results' in page_js
    # 结果详情走 adminResults.detail（results.get 在 api.js 中不存在）
    assert 'Api.endpoints.adminResults.detail' in page_js
    assert 'Api.endpoints.results.get' not in page_js
    # metrics 形状适配：夏普是字典、分布是数组、format 不能进 options 树
    assert 'function periodEntry' in page_js
    assert 'function distValue' in page_js
    assert '$v3ValueLabelFormat' in page_js
    assert 'enabled: true, format' not in page_js

    with open('static/js/common/metric-names.js', encoding='utf-8') as f:
        names_js = f.read()
    assert '基准累计回报率' in names_js
    assert '策略累计回报率' in names_js
    assert '累计超额收益' in names_js
    # v2 页面同步修复后的端点断言
    with open('static/js/pages/performance_analysis_v2.js', encoding='utf-8') as f:
        v2_js = f.read()
    assert 'Api.endpoints.adminResults.detail' in v2_js


def test_xpl_v3_analyze_result_flow_with_series(app_factory):
    """端到端冒烟：结果 ID + include_series → 指标 + 净值序列齐备（页面渲染输入）。"""
    app = app_factory
    with app.app_context():
        task = Task(id="xpl-v3-series-task", name="V3 冒烟任务", task_type="backtest_training", status="completed", config="{}")
        series = TaskResultReturn(
            task_id=task.id,
            **build_return_series_fields(_DUAL_ROWS, stock_code="600519", stock_name="贵州茅台"),
        )
        db.session.add_all([task, series])
        db.session.flush()
        result = TaskResult(
            task_id=task.id,
            step_index=0,
            parameters='{"stock_code":"600519","stock_name":"贵州茅台","year":"2024"}',
            result="{}",
            return_series_id=series.id,
            success=True,
        )
        db.session.add(result)
        db.session.commit()
        result_id = result.id

    headers = _user_headers(app, username="xpl-v3-flow-user")
    body = app.test_client().post(
        '/api/performance-analysis/analyze',
        headers=headers,
        json={"result_id": result_id, "include_series": True},
    ).get_json()

    assert body["status"] == "success"
    results = body["data"]["results"]
    assert results["analysis_mode"] == "dual"
    # KPI 与图表消费的关键键都在
    for key in ("index_cumulative_return", "start_cumulative_return", "excess_cumulative_return",
                "monthly_excess_returns", "index_monthly_distribution", "rolling_return_3_win_rate"):
        assert key in results
    series_payload = body["data"]["series"]
    assert series_payload["dates"] == [row["date"] for row in _DUAL_ROWS]
    assert len(series_payload["start_nav"]) == len(_DUAL_ROWS)
