(function () {
    // 单 Token 子服务模式（2026-09 起）:
    // - 登录经 POST /api/auth/login 由后端代理远程 SysUser/Login，
    //   成功后返回远程颁发的 Token，存于 localStorage.access_token;
    // - 所有同源 fetch 自动附加 `Token` 请求头（旧 Bearer/refresh_token
    //   双令牌流程已移除）; 401 表示 Token 失效，清空登录态并回 /login。
    const TOKEN_KEY = "access_token";
    const THEME_KEY = "templateTheme";
    // 路由表缓存（sessionStorage，随标签页关闭失效）：页面切换时先用
    // 缓存即时渲染侧边栏，避免每次跳转都出现菜单弹出/重排的过程。
    const MENU_CACHE_KEY = "templateMenuRows";
    const originalFetch = window.fetch.bind(window);
    const authExemptPaths = new Set(["/api/auth/login"]);
    const hiddenClassName = "template-auth-hidden";

    let currentUser = null;
    let currentPermissions = [];
    let navItems = [];
    let pagePermissions = [];

    function parseJsonSafely(text) {
        if (!text) {
            return null;
        }
        try {
            return JSON.parse(text);
        } catch (_error) {
            return null;
        }
    }

    function normalizePath(path) {
        if (!path) {
            return "/";
        }
        return path.replace(/\/+$/, "") || "/";
    }

    function sortMenuRows(rows) {
        // 远程返回的路由表本身无序，按文档约定以 order_num 排序（前端完成，
        // 后端为纯代理）；model_id 与数组下标兜底，保证排序稳定。
        const rank = (value) => {
            const parsed = parseInt(value, 10);
            return Number.isNaN(parsed) ? 0 : parsed;
        };
        return rows
            .map((row, index) => ({ row, index }))
            .sort((a, b) =>
                rank(a.row.order_num) - rank(b.row.order_num)
                || rank(a.row.model_id) - rank(b.row.model_id)
                || a.index - b.index
            )
            .map((entry) => entry.row);
    }

    function buildMenuTree(rows) {
        // SIDEBAR-GUIDE.md 第 5 节：平铺数组 → 两级树，顺序跟随返回顺序。
        const model = rows.filter((item) => item.parent_model_id == 0);
        model.forEach((element) => {
            element.children = rows.filter((item) => item.parent_model_id == element.model_id);
        });
        return model;
    }

    // 远程路由表中"退出登录"叶子的约定标识（文档第 10 节建议按 model_code）。
    const LOGOUT_MODEL_CODE = "LoggoutManage";
    const LOGOUT_MODEL_NAME = "退出登录";

    function isLogoutItem(item) {
        return item.model_code === LOGOUT_MODEL_CODE
            || String(item.model_name || "").trim() === LOGOUT_MODEL_NAME;
    }

    function menuLabel(item) {
        return String(item.model_name || item.model_code || "未命名菜单");
    }

    function menuIconHtml(item) {
        const icon = String(item.model_icon || "").trim();
        if (!icon) {
            return "";
        }
        return `<img src="${escapeHtml(icon)}" alt="" onerror="this.remove()">`;
    }

    function getCurrentUrl() {
        return `${window.location.pathname}${window.location.search}`;
    }

    function getLoginUrl() {
        const nextValue = encodeURIComponent(getCurrentUrl());
        return `/login?next=${nextValue}`;
    }

    function getToken() {
        return localStorage.getItem(TOKEN_KEY) || "";
    }

    function setTokens(accessToken) {
        if (accessToken) {
            localStorage.setItem(TOKEN_KEY, accessToken);
        }
    }

    function clearAuthState() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem("refresh_token");
        sessionStorage.removeItem(MENU_CACHE_KEY);
        currentUser = null;
        currentPermissions = [];
        navItems = [];
        pagePermissions = [];
    }

    function isAuthEnabled() {
        const raw = document.body?.dataset?.authEnabled;
        return raw !== "false";
    }

    function isLoginPage() {
        return document.body?.dataset?.pageType === "login";
    }

    function shouldAttachAuth(resource) {
        const requestUrl = new URL(resource, window.location.origin);
        if (requestUrl.origin !== window.location.origin) {
            return false;
        }
        if (requestUrl.pathname.startsWith("/static/")) {
            return false;
        }
        return true;
    }

    function updateBodyReadyState() {
        document.body.classList.remove("template-auth-pending");
        document.body.classList.add(isLoginPage() ? "template-auth-login" : "template-auth-ready");
    }

    function emitAuthReady(detail) {
        document.dispatchEvent(new CustomEvent("template-auth-ready", {
            detail: detail || {},
        }));
    }

    function setLoading(visible, label) {
        const overlay = document.getElementById("templateAuthLoading");
        const labelNode = document.getElementById("templateAuthLoadingLabel");
        if (!overlay) {
            return;
        }
        overlay.classList.toggle("is-visible", Boolean(visible));
        if (labelNode && label) {
            labelNode.textContent = label;
        }
    }

    function showNotification(message, type) {
        if (typeof window.bootstrap === "undefined") {
            window.alert(message);
            return;
        }

        let container = document.getElementById("notification-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "notification-container";
            container.style.position = "fixed";
            container.style.right = "20px";
            container.style.bottom = "20px";
            container.style.zIndex = "2400";
            document.body.appendChild(container);
        }

        const alert = document.createElement("div");
        const alertClass = type === "error"
            ? "alert-danger"
            : type === "success"
                ? "alert-success"
                : type === "warning"
                    ? "alert-warning"
                    : "alert-info";
        alert.className = `alert ${alertClass} alert-dismissible fade show mb-2`;
        alert.style.minWidth = "260px";
        alert.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
        container.appendChild(alert);
        window.setTimeout(() => {
            alert.remove();
        }, 5000);
    }

    function formatTime(timestamp) {
        if (!timestamp) {
            return "-";
        }
        const date = new Date(timestamp);
        if (Number.isNaN(date.getTime())) {
            return "-";
        }
        return date.toLocaleString("zh-CN");
    }

    function getStatusText(status) {
        const textMap = {
            pending: "待执行",
            running: "执行中",
            completed: "已完成",
            cancelled: "已取消",
            error: "执行出错",
        };
        return textMap[status] || status;
    }

    function getStatusClass(status) {
        const classMap = {
            pending: "badge bg-secondary",
            running: "badge bg-warning",
            completed: "badge bg-success",
            cancelled: "badge bg-info",
            error: "badge bg-danger",
        };
        return classMap[status] || "badge bg-secondary";
    }

    function hasPermission(code) {
        if (!code) {
            return true;
        }
        // 本地接口权限仍由后端校验；页面权限用于前端入口可见性。
        if (!String(code).startsWith("page:")) {
            return true;
        }
        if (code === "task:any") {
            return currentPermissions.some((permission) => String(permission).startsWith("task:"));
        }
        return currentPermissions.includes(code);
    }

    function hasAnyPermission(permissionList) {
        if (!permissionList || !permissionList.length) {
            return true;
        }
        return permissionList.some((permission) => hasPermission(permission));
    }

    function escapeHtml(text) {
        return String(text || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function getPagePermissions() {
        const datasetValue = (document.body?.dataset?.requiredPermissions || "")
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean);
        if (datasetValue.length) {
            return datasetValue;
        }
        const pathname = window.location.pathname;
        if (/^\/google-sheet(?:\/|$)/.test(pathname)) {
            const path = `/google-sheet/?version=${new URLSearchParams(window.location.search).get("version") || "c3"}`;
            const page = pagePermissions.find((item) => item.path === path);
            return page ? [page.permission] : [];
        }
        const currentUrl = getCurrentUrl();
        const page = pagePermissions.find((item) => item.path === currentUrl)
            || pagePermissions.find((item) => normalizePath(item.path) === normalizePath(pathname));
        return page ? [page.permission] : [];
    }

    function redirectToLogin() {
        if (!isLoginPage()) {
            window.location.replace(getLoginUrl());
        }
    }

    async function authFetch(resource, init) {
        const request = init ? { ...init } : {};
        const resourceUrl = resource instanceof Request ? resource.url : resource;
        const attachAuth = shouldAttachAuth(resourceUrl);
        const requestUrl = new URL(resourceUrl, window.location.origin);
        const path = requestUrl.pathname;
        const headers = new Headers(request.headers || (resource instanceof Request ? resource.headers : undefined) || undefined);

        if (attachAuth && getToken() && !authExemptPaths.has(path)) {
            headers.set("Token", getToken());
        }
        request.headers = headers;

        const response = await originalFetch(resource, request);
        if (
            response.status !== 401 ||
            !attachAuth ||
            authExemptPaths.has(path)
        ) {
            return response;
        }

        // 单 Token 模式: 无 refresh 流程, Token 失效即清空登录态并回登录页。
        clearAuthState();
        redirectToLogin();
        return response;
    }

    window.fetch = authFetch;

    async function requestJson(url, options) {
        const response = await authFetch(url, options);
        const text = await response.text();
        const payload = parseJsonSafely(text);
        if (!response.ok) {
            const error = new Error((payload && payload.message) || `Request failed with status ${response.status}`);
            error.response = response;
            error.payload = payload;
            throw error;
        }
        return payload;
    }

    function ajaxRequest(url, method, data, callback) {
        const options = { method: method || "GET" };
        if (data instanceof FormData) {
            options.body = data;
        } else if (data !== null && data !== undefined) {
            options.body = JSON.stringify(data);
            options.headers = {
                "Content-Type": "application/json",
            };
        }

        requestJson(url, options)
            .then((payload) => callback(null, payload))
            .catch((error) => callback(error, error.payload || null));
    }

    function updateUserPanels() {
        const username = currentUser?.username || "未登录";
        const roles = Array.isArray(currentUser?.roles) && currentUser.roles.length
            ? currentUser.roles.map((role) => role.name || role.code).join(" / ")
            : "当前账户";

        document.querySelectorAll("[data-template-auth-username]").forEach((node) => {
            node.textContent = username;
        });
        document.querySelectorAll("[data-template-auth-role]").forEach((node) => {
            node.textContent = roles;
        });
        document.querySelectorAll("[data-template-auth-avatar]").forEach((node) => {
            node.textContent = username.slice(0, 2).toUpperCase();
        });
    }

    function isItemActive(path) {
        if (!path) {
            return false;
        }
        const currentPath = `${window.location.pathname}${window.location.search}`;
        const normalizedCurrent = normalizePath(currentPath);
        const normalizedTarget = normalizePath(path);
        return normalizedCurrent === normalizedTarget || currentPath === path;
    }

    function readSavedCollapseState() {
        const saved = parseJsonSafely(localStorage.getItem("sidebarCollapseState"));
        return saved && typeof saved === "object" ? saved : {};
    }

    function renderSidebarMenu(tree) {
        const container = document.getElementById("templateSidebarMenu");
        if (!container) {
            return;
        }

        if (!tree.length) {
            container.innerHTML = '<div class="template-auth-empty-nav px-2 py-3">当前账号暂无可见菜单</div>';
            return;
        }

        // 折叠状态在渲染时直接写入初始 HTML（按 model_id 记忆），不渲染后再
        // 补 class，页面切换重建侧边栏时不会触发 Bootstrap 展开动画。
        const savedCollapse = readSavedCollapseState();
        const hasActiveDescendant = (item) => isItemActive(item.model_link || "")
            || (item.children || []).some(hasActiveDescendant);
        const renderItem = (item, nested) => {
            const label = escapeHtml(menuLabel(item));
            const icon = menuIconHtml(item);
            // 远程路由表的"退出登录"叶子：渲染为登出触发项而非页面跳转，
            // 点击行为由 bindLogoutButtons 统一绑定（清 Token 并回 /login）。
            if (isLogoutItem(item)) {
                return `<li><a class="nav-link text-danger" href="#" data-template-auth-logout>${icon}<span>${label}</span></a></li>`;
            }
            if (!item.children?.length) {
                const link = String(item.model_link || "");
                return link
                    ? `<li><a class="nav-link ${isItemActive(link) ? "active" : ""}" href="${escapeHtml(link)}">${icon}<span>${label}</span></a></li>`
                    : `<li><span class="nav-link disabled">${icon}<span>${label}</span></span></li>`;
            }
            const collapseId = `templateSidebarGroup${item.model_id}`;
            const savedExpanded = savedCollapse[collapseId];
            const expanded = savedExpanded !== undefined
                ? Boolean(savedExpanded)
                : hasActiveDescendant(item);
            return `<li class="${nested ? "mt-1" : "mt-3"}">
                <button class="btn-toggle" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${expanded ? "true" : "false"}">
                    <span>${icon}${label}</span><i class="bi bi-chevron-right btn-toggle-icon"></i>
                </button>
                <div class="collapse ${expanded ? "show" : ""}" id="${collapseId}"><ul class="btn-toggle-nav">${item.children.map((child) => renderItem(child, true)).join("")}</ul></div>
            </li>`;
        };
        container.innerHTML = `<ul class="btn-toggle-nav">${tree.map((item) => renderItem(item, false)).join("")}</ul>`;
    }

    function renderTopMenu(tree) {
        const container = document.getElementById("templateTopMenu");
        if (!container) {
            return;
        }

        const leaves = [];
        const collectLeaves = (items) => {
            (items || []).forEach((item) => {
                if (item.children?.length) {
                    collectLeaves(item.children);
                } else {
                    leaves.push(item);
                }
            });
        };
        collectLeaves(tree);

        const renderLeaf = (item) => {
            const label = escapeHtml(menuLabel(item));
            if (isLogoutItem(item)) {
                return `<a class="nav-link text-danger" href="#" data-template-auth-logout>${label}</a>`;
            }
            const link = String(item.model_link || "");
            if (!link) {
                return `<span class="nav-link disabled">${label}</span>`;
            }
            return `<a class="nav-link ${isItemActive(link) ? "active" : ""}" href="${escapeHtml(link)}">${label}</a>`;
        };

        const isListContainer = container.tagName === "UL" || container.tagName === "OL";

        if (!leaves.length) {
            container.innerHTML = isListContainer
                ? '<li class="nav-item"><span class="nav-link disabled">当前账号暂无可见菜单</span></li>'
                : '<span class="template-auth-empty-nav">当前账号暂无可见菜单</span>';
            return;
        }

        if (isListContainer) {
            container.innerHTML = leaves.map((item) => `<li class="nav-item">${renderLeaf(item)}</li>`).join("");
            return;
        }

        container.classList.add("template-auth-horizontal-nav");
        container.innerHTML = leaves.map(renderLeaf).join("");
    }

    function ensureFloatingEntry() {
        if (!document.body?.dataset?.templateAuthFloatingNav) {
            return;
        }
        if (document.getElementById("templateAuthFloatingEntry")) {
            return;
        }

        const button = document.createElement("button");
        button.id = "templateAuthFloatingEntry";
        button.className = "btn btn-primary rounded-pill shadow template-auth-floating-entry";
        button.type = "button";
        button.innerHTML = '<i class="bi bi-grid-3x3-gap"></i> 菜单';

        const panel = document.createElement("div");
        panel.id = "templateAuthFloatingPanel";
        panel.className = "template-auth-floating-panel";
        panel.innerHTML = `
            <div class="d-flex justify-content-between align-items-start mb-3">
                <div>
                    <div class="fw-semibold template-auth-user__name" data-template-auth-username>未登录</div>
                    <div class="small template-auth-user__meta" data-template-auth-role>当前账户</div>
                </div>
                <button type="button" class="btn btn-sm btn-outline-secondary" data-template-auth-logout>退出</button>
            </div>
            <div id="templateTopMenu"></div>
        `;

        button.addEventListener("click", function () {
            panel.classList.toggle("is-visible");
        });

        document.body.appendChild(button);
        document.body.appendChild(panel);
    }

    function applyMenuRows(rows) {
        navItems = buildMenuTree(sortMenuRows(Array.isArray(rows) ? rows : []));
        renderSidebarMenu(navItems);
        renderTopMenu(navItems);
    }

    async function loadNav() {
        // 1) 先用 sessionStorage 缓存即时渲染：MPA 每次页面切换都会重建
        //    侧边栏，缓存命中时菜单随页面同步出现，无弹出/重排过程。
        const cachedRows = parseJsonSafely(sessionStorage.getItem(MENU_CACHE_KEY));
        if (Array.isArray(cachedRows) && cachedRows.length) {
            applyMenuRows(cachedRows);
        }

        // 2) 再拉取最新路由表；仅在与缓存不一致时重绘，避免无谓重渲染。
        try {
            const payload = await requestJson("/api/meta/nav", { method: "GET" });
            const navigationData = payload?.data || {};
            const rows = Array.isArray(navigationData)
                ? navigationData
                : navigationData.items || [];
            if (JSON.stringify(rows) !== JSON.stringify(cachedRows || null)) {
                sessionStorage.setItem(MENU_CACHE_KEY, JSON.stringify(rows));
                applyMenuRows(rows);
            }
        } catch (error) {
            // 401 表示 Token 失效，抛回由统一流程清空登录态并回登录页；
            // 其余失败（如远程菜单服务暂不可用）不强制登出：有缓存时静默
            // 沿用缓存，无缓存时提示后保留会话。
            if (error?.response?.status === 401) {
                throw error;
            }
            if (!Array.isArray(cachedRows) || !cachedRows.length) {
                showNotification(error.message || "菜单加载失败，请稍后刷新重试", "error");
            }
        }
    }

    function applyPermissionNodes() {
        const nodes = document.querySelectorAll("[data-permission]");
        nodes.forEach((node) => {
            const raw = node.getAttribute("data-permission") || "";
            const permissions = raw.split(",").map((value) => value.trim()).filter(Boolean);
            const allowed = hasAnyPermission(permissions);
            if (allowed) {
                node.classList.remove(hiddenClassName);
                node.removeAttribute("hidden");
            } else {
                node.classList.add(hiddenClassName);
                node.setAttribute("hidden", "hidden");
            }
        });
    }

    function renderForbiddenState(requiredPermissions) {
        const container = document.querySelector("[data-template-main-content]") || document.querySelector("main");
        if (!container) {
            showNotification("当前账号没有页面访问权限", "error");
            return;
        }

        const permissions = Array.isArray(requiredPermissions) ? requiredPermissions.filter(Boolean) : [];
        const missingPermissions = permissions.filter((permission) => !hasPermission(permission));
        const requirementText = permissions.length > 1
            ? `需要以下任一权限: ${permissions.join(" 或 ")}`
            : permissions.length === 1
                ? `需要权限: ${permissions[0]}`
                : "当前页面未声明所需权限";
        const missingText = missingPermissions.length
            ? missingPermissions.join("、")
            : "未知（请联系管理员检查页面权限配置）";

        container.innerHTML = `
            <div class="template-auth-guard">
                <div class="display-6 mb-3">403</div>
                <h2 class="h4 mb-3">当前账号没有此页面访问权限</h2>
                <p class="text-muted mb-2">${escapeHtml(requirementText)}</p>
                <p class="text-muted mb-4">当前缺少: ${escapeHtml(missingText)}</p>
                <a class="btn btn-primary" href="/admin/">返回首页</a>
            </div>
        `;
    }

    function bindLogoutButtons() {
        document.querySelectorAll("[data-template-auth-logout]").forEach((button) => {
            button.addEventListener("click", async function () {
                try {
                    if (getToken()) {
                        await requestJson("/api/auth/logout", { method: "POST" });
                    }
                } catch (_error) {
                    // Ignore logout failures and still clear client state.
                } finally {
                    clearAuthState();
                    window.location.replace("/login");
                }
            });
        });
    }

    function applyTheme(theme) {
        const normalized = theme === "dark" ? "dark" : "light";
        document.documentElement.setAttribute("data-bs-theme", normalized);
        localStorage.setItem(THEME_KEY, normalized);

        document.querySelectorAll("[data-template-theme-toggle]").forEach((node) => {
            node.textContent = normalized === "dark" ? "切换浅色" : "切换深色";
        });
        document.querySelectorAll("[data-template-theme-icon]").forEach((node) => {
            node.className = normalized === "dark" ? "bi bi-sun-fill" : "bi bi-moon-stars-fill";
        });
    }

    function bindThemeToggles() {
        document.querySelectorAll("[data-template-theme-trigger]").forEach((button) => {
            button.addEventListener("click", function () {
                const current = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "dark" : "light";
                applyTheme(current === "dark" ? "light" : "dark");
            });
        });
    }

    async function fetchCurrentUser() {
        const payload = await requestJson("/api/auth/me", { method: "GET" });
        currentUser = payload?.data || null;
        currentPermissions = Array.isArray(currentUser?.permissions) ? currentUser.permissions : [];
        updateUserPanels();
        applyPermissionNodes();
        return currentUser;
    }

    function getLoginNextUrl() {
        const nextFromInput = document.getElementById("loginNextUrl");
        if (nextFromInput?.value) {
            return nextFromInput.value;
        }
        const params = new URLSearchParams(window.location.search);
        return params.get("next") || "/admin/";
    }

    function bindLoginPage() {
        applyTheme(localStorage.getItem(THEME_KEY) || "light");
        bindThemeToggles();
        updateBodyReadyState();

        const form = document.getElementById("templateLoginForm");
        const submitButton = document.getElementById("templateLoginSubmit");
        const errorBox = document.getElementById("templateLoginError");
        if (!form || !submitButton) {
            return;
        }

        if (!isAuthEnabled()) {
            window.location.replace(getLoginNextUrl());
            return;
        }

        if (getToken()) {
            fetchCurrentUser()
                .then(() => {
                    window.location.replace(getLoginNextUrl());
                })
                .catch(() => {
                    clearAuthState();
                });
        }

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            errorBox.classList.add("d-none");
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>登录中...';

            const formData = new FormData(form);
            const username = String(formData.get("username") || "").trim();
            const password = String(formData.get("password") || "");

            try {
                const payload = await requestJson("/api/auth/login", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ username, password }),
                });
                const data = payload?.data || {};
                setTokens(data.access_token, data.refresh_token);
                currentUser = data.user || null;
                currentPermissions = Array.isArray(data.user?.permissions) ? data.user.permissions : [];
                window.location.replace(getLoginNextUrl());
            } catch (error) {
                errorBox.textContent = error.message || "登录失败，请检查用户名和密码";
                errorBox.classList.remove("d-none");
            } finally {
                submitButton.disabled = false;
                submitButton.textContent = "登录";
            }
        });
    }

    async function bootstrapProtectedPage() {
        ensureFloatingEntry();
        applyTheme(localStorage.getItem(THEME_KEY) || "light");
        bindThemeToggles();

        if (!isAuthEnabled()) {
            updateBodyReadyState();
            bindLogoutButtons();
            emitAuthReady({ authEnabled: false, user: currentUser, permissions: currentPermissions.slice() });
            return;
        }

        if (!getToken()) {
            redirectToLogin();
            return;
        }

        setLoading(true, "正在恢复登录状态...");
        try {
            await fetchCurrentUser();
            await loadNav();
            bindLogoutButtons();

            const permissions = getPagePermissions();
            if (!hasAnyPermission(permissions)) {
                renderForbiddenState(permissions);
            }
            updateBodyReadyState();
            emitAuthReady({ authEnabled: true, user: currentUser, permissions: currentPermissions.slice() });
        } catch (_error) {
            clearAuthState();
            redirectToLogin();
            return;
        } finally {
            setLoading(false);
        }
    }

    function injectHiddenPermissionStyle() {
        if (document.getElementById("templateAuthHiddenStyle")) {
            return;
        }
        const style = document.createElement("style");
        style.id = "templateAuthHiddenStyle";
        style.textContent = `.${hiddenClassName}{display:none !important;}`;
        document.head.appendChild(style);
    }

    document.addEventListener("DOMContentLoaded", function () {
        injectHiddenPermissionStyle();
        if (isLoginPage()) {
            bindLoginPage();
            return;
        }
        bootstrapProtectedPage();
    });

    window.TemplateApp = {
        ajaxRequest,
        showNotification,
        showError(message) {
            showNotification(message, "error");
        },
        formatTime,
        getStatusText,
        getStatusClass,
        getCurrentUser() {
            return currentUser;
        },
        getPermissions() {
            return currentPermissions.slice();
        },
        hasPermission,
        requestJson,
    };

    if (document.body?.dataset?.templateAuthExposeHelpers !== "false") {
        window.ajaxRequest = ajaxRequest;
        window.showNotification = showNotification;
        window.showError = window.TemplateApp.showError;
        window.formatTime = formatTime;
        window.getStatusText = getStatusText;
        window.getStatusClass = getStatusClass;
    }
})();
