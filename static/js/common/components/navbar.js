// 导航条组件（docs/design/frontend-refactor/02 §3.7，D6 修订）。
// 三套基座导航合一：内置各族菜单配置，按 location.pathname 前缀选族渲染；
// 页面 HTML 中基座导航整段替换为 <div data-navbar></div> 占位。
// 渲染产物与原基座导航逐字节等价（结构/class/属性一致，active 与徽标按 URL 计算）；
// 渲染在鉴权揭示前完成（body 仍带 template-auth-pending），无首屏闪动。
// 引入顺序：template-auth.js → navbar.js → api.js → utils.js → 页面 JS。
'use strict';

(function () {
    // ── google_sheet 族（原 google_sheet/base.html:28-109 导航）──
    // active/徽标/href 的 version 分支与原 Jinja 逐条等价迁移。
    function googleSheetMenu() {
        const params = new URLSearchParams(window.location.search);
        const version = params.get('version');
        // 原 Jinja：request.endpoint == 'google_sheet.index' and not version → 首页 active
        const isIndex = window.location.pathname.replace(/\/+$/, '') === '/google-sheet';
        const withVersion = function (path) {
            return version ? path + '?version=' + encodeURIComponent(version) : path;
        };
        const item = function (href, permission, icon, label, active) {
            return '<li class="nav-item">' +
                '<a class="nav-link' + (active ? ' active' : '') + '"' +
                ' data-permission="' + permission + '"' +
                ' href="' + href + '">' +
                '<i class="bi ' + icon + '"></i> ' + label +
                '</a></li>';
        };
        // 原 Jinja 首页 data-permission：c4 → page:google_sheet:c4，c5 → c5，其余 c3
        const homePermission =
            version === 'c4' ? 'page:google_sheet:c4' :
            version === 'c5' ? 'page:google_sheet:c5' : 'page:google_sheet:c3';
        const menu =
            '<ul class="navbar-nav me-auto">' +
            item(withVersion('/google-sheet/'), homePermission, 'bi-house', '首页', isIndex && !version) +
            item('/google-sheet/?version=c3', 'page:google_sheet:c3', 'bi-lightning-charge', 'C3 模式', version === 'c3') +
            item('/google-sheet/?version=c4', 'page:google_sheet:c4', 'bi-lightning-charge', 'C4 模式', version === 'c4') +
            item('/google-sheet/?version=c5', 'page:google_sheet:c5', 'bi-lightning-charge', 'C5 模式', version === 'c5') +
            item('/google-sheet/?version=c7', 'page:google_sheet:c7', 'bi-lightning-charge', 'C7 模式', version === 'c7') +
            '</ul>';
        // 原 Jinja 徽标分支表：c4/c5 → bg-warning，c7 → bg-danger，c3 → bg-success，其余 bg-secondary
        let badgeClass = 'bg-secondary';
        let badgeText = '基础模式';
        if (version === 'c4' || version === 'c5') {
            badgeClass = 'bg-warning';
            badgeText = version.toUpperCase() + ' 模式';
        } else if (version === 'c7') {
            badgeClass = 'bg-danger';
            badgeText = 'C7 模式';
        } else if (version === 'c3') {
            badgeClass = 'bg-success';
            badgeText = 'C3 模式';
        }
        const badge =
            '<div class="navbar-text me-3">' +
            '<span class="badge ' + badgeClass + '">' + badgeText + '</span>' +
            '</div>';
        const right =
            '<ul class="navbar-nav align-items-lg-center">' +
            '<li class="nav-item">' +
            '<a class="nav-link" data-permission="page:admin:dashboard" href="/admin/">' +
            '<i class="bi bi-gear"></i> 管理面板' +
            '</a></li>' +
            '<li class="nav-item dropdown">' +
            '<a class="nav-link dropdown-toggle d-flex align-items-center gap-2" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">' +
            '<span class="badge rounded-pill bg-light text-dark" data-template-auth-avatar>AI</span>' +
            '<span class="d-none d-lg-inline" data-template-auth-username>占位用户</span>' +
            '</a>' +
            '<ul class="dropdown-menu dropdown-menu-end">' +
            '<li><span class="dropdown-item-text text-muted" data-template-auth-role>当前账户</span></li>' +
            '<li><hr class="dropdown-divider"></li>' +
            '<li><button type="button" class="dropdown-item d-flex align-items-center gap-2" data-template-theme-trigger>' +
            '<i class="bi bi-circle-half" data-template-theme-icon></i>' +
            '<span data-template-theme-toggle>切换主题</span>' +
            '</button></li>' +
            '<li><button type="button" class="dropdown-item text-danger" data-template-auth-logout>退出登录</button></li>' +
            '</ul></li></ul>';
        return '<div class="container">' +
            '<button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">' +
            '<span class="navbar-toggler-icon"></span>' +
            '</button>' +
            '<div class="collapse navbar-collapse" id="navbarNav">' +
            menu + badge + right +
            '</div></div>';
    }

    // ── admin 族（原 admin/base.html:366-398 侧栏外壳）──
    // 纯静态外壳（品牌区 + 空 #templateSidebarMenu + 用户下拉），零 Jinja；
    // 菜单项仍由 template-auth.js 经 /api/meta/nav 渲染进 #templateSidebarMenu，
    // active 类由其按 pathname+search 计算（admin-shell.js 只负责折叠态记忆，均在
    // navbar.js 之后加载，渲染时序不受影响）。
    function adminSidebar() {
        return '<div class="position-sticky d-flex flex-column min-vh-100 px-3 pt-4 pb-3">' +
            '<div class="d-flex align-items-center gap-3 px-2 pb-3 mb-3 border-bottom">' +
            '<div class="sidebar-brand-icon">' +
            '<i class="bi bi-grid-1x2-fill"></i>' +
            '</div>' +
            '<div>' +
            '<p class="mb-0 fw-bold text-body">Jaspil 任务平台</p>' +
            '<p class="mb-0 mt-1 small text-muted">Operations Platform</p>' +
            '</div>' +
            '</div>' +
            '<div class="nav flex-column flex-grow-1" id="templateSidebarMenu"></div>' +
            '<div class="mt-3 pt-3 border-top flex-shrink-0">' +
            '<div class="dropup">' +
            '<button class="btn btn-link dropdown-toggle d-flex align-items-center gap-2 w-100 px-0 py-1 text-start text-decoration-none text-reset border-0 shadow-none" type="button" data-bs-toggle="dropdown" aria-expanded="false">' +
            '<div class="sidebar-user-avatar" data-template-auth-avatar>AI</div>' +
            '<div class="flex-grow-1 min-w-0">' +
            '<div class="fw-semibold text-truncate" data-template-auth-username>占位用户</div>' +
            '<div class="small text-muted text-truncate" data-template-auth-role>Jaspil 用户</div>' +
            '</div>' +
            '</button>' +
            '<ul class="dropdown-menu w-100 shadow">' +
            '<li>' +
            '<button type="button" class="dropdown-item d-flex align-items-center gap-2" data-template-theme-trigger>' +
            '<i class="bi bi-circle-half" data-template-theme-icon></i>' +
            '<span data-template-theme-toggle>切换主题</span>' +
            '</button>' +
            '</li>' +
            '<li><hr class="dropdown-divider"></li>' +
            '<li><button type="button" class="dropdown-item text-danger" data-template-auth-logout>退出登录</button></li>' +
            '</ul>' +
            '</div>' +
            '</div>' +
            '</div>';
    }

    const FAMILIES = [
        { prefixes: ['/google-sheet'], build: googleSheetMenu },
        // admin 基座族：挂载点本身就是 <nav class="sidebar ...">，渲染时保留原 class（02 §3.7 渲染等价红线）
        {
            prefixes: ['/admin', '/performance_analysis', '/backtest-training', '/backtest-multi-product', '/global-preview'],
            build: adminSidebar,
            classes: 'col-md-3 col-lg-2 d-md-block sidebar collapse',
        },
    ];

    function render() {
        const mount = document.querySelector('[data-navbar]');
        if (!mount) return;
        const path = window.location.pathname;
        const family = FAMILIES.find(function (f) {
            return f.prefixes.some(function (p) { return path.indexOf(p) === 0; });
        });
        if (!family) {
            // 未登记的路径不做渲染（独立页/admin 基座未迁移时保持各自的导航标记）。
            mount.remove();
            return;
        }
        mount.className = family.classes || 'navbar navbar-expand-lg navbar-dark bg-primary';
        mount.removeAttribute('data-navbar');
        mount.innerHTML = family.build();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', render);
    } else {
        render();
    }
})();
