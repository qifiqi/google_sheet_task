"""前端静态化回归守卫（docs/design/frontend-refactor）。

已静态化的页面经 send_page 返回：200、text/html、零 Jinja 残留、
按序引入 common/pages 脚本。每完成一批（F1~F5）在此登记对应页面。
"""
import pytest

from app.extensions import db
from app.models import User
from app.utils.auth import create_access_token

# (页面 URL, 页面 JS 文件[, require_common_scripts])；随批次推进追加。
# require_common_scripts=False 用于独立页（不加载 common/api.js）。
STATIC_PAGES = [
    # F1: google_sheet/merge_export.html
    ("/google-sheet/merge-export", "/static/js/pages/google_sheet_merge_export.js"),
    # F2: google_sheet/index.html + create.html(C3) + detail.html + google_sheet_c31/create.html
    ("/google-sheet/", "/static/js/pages/google_sheet_index.js"),
    ("/google-sheet/create", "/static/js/pages/google_sheet_create.js"),
    ("/google-sheet/create?version=c31", "/static/js/pages/google_sheet_c31_create.js"),
    ("/google-sheet/detail", "/static/js/pages/google_sheet_detail.js"),
    # F2: dispatcher 页（无 version 时按 task/restart_task 查询后重定向的跳板页）
    ("/google-sheet/create?restart_task_id=static-fixture", "/static/js/pages/google_sheet_create_dispatcher.js"),
    ("/google-sheet/detail?task_id=static-fixture", "/static/js/pages/google_sheet_detail_dispatcher.js"),
    # F3: google_sheet_c4/c5/c7 六大页（create + detail）
    ("/google-sheet/create?version=c4", "/static/js/pages/google_sheet_c4_create.js"),
    ("/google-sheet/create?version=c5", "/static/js/pages/google_sheet_c5_create.js"),
    ("/google-sheet/create?version=c7", "/static/js/pages/google_sheet_c7_create.js"),
    ("/google-sheet/detail?version=c4", "/static/js/pages/google_sheet_c4_detail.js"),
    ("/google-sheet/detail?version=c5", "/static/js/pages/google_sheet_c5_detail.js"),
    ("/google-sheet/detail?version=c7", "/static/js/pages/google_sheet_c7_detail.js"),
    # F4: backtest_training 六页（backtest 双胞胎 + global_preview 批次）
    ("/backtest-training/create", "/static/js/pages/backtest_training_create.js"),
    ("/backtest-training/list", "/static/js/pages/backtest_training_list.js"),
    ("/backtest-training/detail/bt-task-1", "/static/js/pages/backtest_training_detail.js"),
    ("/backtest-training/global-preview/bt-task-1", "/static/js/pages/backtest_training_global_preview.js"),
    ("/backtest-training/result/123", "/static/js/pages/backtest_training_result.js"),
    ("/backtest-training/result/123/export-preview", "/static/js/pages/backtest_training_result_export_preview.js"),
    # F4: backtest_multi_product 五页
    ("/backtest-multi-product/create", "/static/js/pages/backtest_multi_product_create.js"),
    ("/backtest-multi-product/list", "/static/js/pages/backtest_multi_product_list.js"),
    ("/backtest-multi-product/detail/bt-task-1", "/static/js/pages/backtest_multi_product_detail.js"),
    ("/backtest-multi-product/global-preview/bt-task-1", "/static/js/pages/backtest_multi_product_global_preview.js"),
    ("/backtest-multi-product/result/123", "/static/js/pages/backtest_multi_product_result.js"),
    # F4: global_preview 独立入口
    ("/global-preview/single_product", "/static/js/pages/global_preview_index.js"),
    # F5: admin 族 13 页（基座已内联展开 + admin-shell.js；导航条由 navbar.js 渲染）
    ("/admin/", "/static/js/pages/admin_dashboard.js"),
    ("/admin/tasks", "/static/js/pages/admin_tasks.js"),
    ("/admin/config", "/static/js/pages/admin_config.js"),
    ("/admin/logs", "/static/js/pages/admin_logs.js"),
    ("/admin/results", "/static/js/pages/admin_results.js"),
    ("/admin/navigation", "/static/js/pages/admin_navigation.js"),
    ("/admin/templates", "/static/js/pages/admin_templates.js"),
    ("/admin/scheduler", "/static/js/pages/admin_scheduler.js"),
    ("/admin/model-summary", "/static/js/pages/admin_model_summary.js"),
    ("/admin/google-sheets", "/static/js/pages/admin_google_sheets.js"),
    ("/admin/roles", "/static/js/pages/admin_roles.js"),
    ("/admin/users", "/static/js/pages/admin_users.js"),
    # /admin/eastmoney-kline 为纯 iframe 壳页，无页面 JS，仅断言 pages css 与零 Jinja
    ("/admin/eastmoney-kline", "/static/css/pages/admin_eastmoney_kline.css", False),
    # F5: xpl 三页（基座内联展开；CDN jquery/datatables/chart.js 保留外链）
    ("/xpl/", "/static/js/pages/xpl_index.js"),
    ("/xpl/v1", "/static/js/pages/xpl_v1.js"),
    ("/xpl/v2", "/static/js/pages/xpl_v2.js"),
    # F5: yule 两页（sjxz 独立页保留 floating-nav 属性；index 为跳转壳）
    ("/yule/", "/static/js/pages/yule_index.js", False),
    ("/yule/sjxz", "/static/js/pages/yule_sjxz.js", False),
    # F5: eastmoney_kline 独立页（已模块化，自带 layui/utils 脚本）
    ("/eastmoney-kline", "/static/js/pages/eastmoney_kline_index.js", False),
    # F5: 登录页（独立页，loginNextUrl 由 login.js 从 ?next= 填充）
    ("/login", "/static/js/pages/login.js", False),
]

# 2 元组条目默认加载 common/api.js；独立页显式给 require_common_scripts=False
STATIC_PAGES = [e if len(e) == 3 else (e[0], e[1], True) for e in STATIC_PAGES]


@pytest.fixture()
def _page_user(app_factory):
    with app_factory.app_context():
        user = User(username="static-page-user", password_hash="x")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(user.id, token_version=user.token_version)
        yield {"headers": {"Authorization": f"Bearer {token}"}}


@pytest.mark.parametrize("url,page_js,require_common", STATIC_PAGES)
def test_static_page_served_without_jinja(app_factory, _page_user, url, page_js, require_common):
    app = app_factory
    client = app.test_client()

    response = client.get(url, headers=_page_user["headers"])

    assert response.status_code == 200
    assert "text/html" in response.content_type
    body = response.get_data(as_text=True)
    assert "{{" not in body and "{%" not in body
    assert "data-auth-enabled" not in body
    assert page_js in body
    if require_common:
        assert "/static/js/common/api.js" in body
