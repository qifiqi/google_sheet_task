(function () {
    const TOKEN_KEY = "access_token";
    const REFRESH_KEY = "refresh_token";
    const THEME_KEY = "templateTheme";
    const originalFetch = window.fetch.bind(window);
    const authExemptPaths = new Set(["/api/auth/login", "/api/auth/refresh"]);
    const hiddenClassName = "template-auth-hidden";

    let currentUser = null;
    let currentPermissions = [];
    let isRefreshing = false;
    let refreshPromise = null;
    let navItems = [];

    const legacyPathMap = new Map([
        ["/admin", "/admin/"],
        ["/task/list?version=c3", "/google-sheet/?version=c3"],
        ["/task/list?version=c4", "/google-sheet/?version=c4"],
        ["/task/list?version=c5", "/google-sheet/?version=c5"],
        ["/task/create", "/google-sheet/create"],
        ["/backtest/list", "/backtest-training/list"],
        ["/backtest/create", "/backtest-training/create"],
        ["/xpl", "/xpl/"],
    ]);

    const templateUnsupportedPaths = new Set([]);

    const pagePermissionMatchers = [
        { test: /^\/admin\/?$/, permissions: ["page:admin:dashboard"] },
        { test: /^\/admin\/tasks\/?$/, permissions: ["page:admin:tasks"] },
        { test: /^\/admin\/config\/?$/, permissions: ["page:admin:config"] },
        { test: /^\/admin\/navigation\/?$/, permissions: ["page:admin:navigation"] },
        { test: /^\/admin\/logs\/?$/, permissions: ["page:admin:logs"] },
        { test: /^\/admin\/templates\/?$/, permissions: ["page:admin:templates"] },
        { test: /^\/admin\/results\/?$/, permissions: ["page:admin:results"] },
        { test: /^\/admin\/google-sheets\/?$/, permissions: ["page:admin:google_sheets"] },
        { test: /^\/admin\/scheduler\/?$/, permissions: ["page:admin:scheduler"] },
        { test: /^\/admin\/users\/?$/, permissions: ["page:admin:users"] },
        { test: /^\/admin\/roles\/?$/, permissions: ["page:admin:roles"] },
        { test: /^\/backtest-training\/list\/?$/, permissions: ["page:backtest:list"] },
        { test: /^\/backtest-training\/create\/?$/, permissions: ["page:backtest:create"] },
        { test: /^\/backtest-training\/detail\/.+$/, permissions: ["page:backtest:list"] },
        { test: /^\/backtest-training\/global-preview\/.+$/, permissions: ["page:backtest:list"] },
        { test: /^\/backtest-training\/result\/.+$/, permissions: ["page:backtest:list"] },
    ];

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

    function getRefreshToken() {
        return localStorage.getItem(REFRESH_KEY) || "";
    }

    function setTokens(accessToken, refreshToken) {
        if (accessToken) {
            localStorage.setItem(TOKEN_KEY, accessToken);
        }
        if (refreshToken) {
            localStorage.setItem(REFRESH_KEY, refreshToken);
        }
    }

    function clearAuthState() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
        currentUser = null;
        currentPermissions = [];
        navItems = [];
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

    function getGoogleSheetPermissionByVersion() {
        const version = (new URLSearchParams(window.location.search).get("version") || "c3").toLowerCase();
        if (version === "c4") {
            return "page:google_sheet:c4";
        }
        if (version === "c5") {
            return "page:google_sheet:c5";
        }
        if (version === "c31") {
            return "page:google_sheet:c3";
        }
        return "page:google_sheet:c3";
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
            return [getGoogleSheetPermissionByVersion()];
        }
        const matcher = pagePermissionMatchers.find((item) => item.test.test(pathname));
        return matcher ? matcher.permissions : [];
    }

    function redirectToLogin() {
        if (!isLoginPage()) {
            window.location.replace(getLoginUrl());
        }
    }

    async function performRefresh() {
        const refreshToken = getRefreshToken();
        if (!refreshToken) {
            throw new Error("missing refresh token");
        }

        const response = await originalFetch("/api/auth/refresh", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ refresh_token: refreshToken }),
        });

        const payload = parseJsonSafely(await response.text());
        if (!response.ok || !payload || payload.code !== 0) {
            throw new Error((payload && payload.message) || "refresh failed");
        }

        const data = payload.data || {};
        setTokens(data.access_token, refreshToken);
        currentUser = data.user || currentUser;
        currentPermissions = Array.isArray(data.user?.permissions) ? data.user.permissions : currentPermissions;
        updateUserPanels();
        applyPermissionNodes();
        return data.access_token;
    }

    async function refreshAccessToken() {
        if (isRefreshing && refreshPromise) {
            return refreshPromise;
        }

        isRefreshing = true;
        refreshPromise = performRefresh()
            .finally(() => {
                isRefreshing = false;
                refreshPromise = null;
            });
        return refreshPromise;
    }

    async function authFetch(resource, init) {
        const request = init ? { ...init } : {};
        const resourceUrl = resource instanceof Request ? resource.url : resource;
        const attachAuth = shouldAttachAuth(resourceUrl);
        const requestUrl = new URL(resourceUrl, window.location.origin);
        const path = requestUrl.pathname;
        const headers = new Headers(request.headers || (resource instanceof Request ? resource.headers : undefined) || undefined);

        if (attachAuth && getToken() && !authExemptPaths.has(path)) {
            headers.set("Authorization", `Bearer ${getToken()}`);
        }
        request.headers = headers;

        const response = await originalFetch(resource, request);
        if (
            response.status !== 401 ||
            !attachAuth ||
            authExemptPaths.has(path) ||
            request._retry
        ) {
            return response;
        }

        try {
            const newToken = await refreshAccessToken();
            const retryHeaders = new Headers(headers);
            retryHeaders.set("Authorization", `Bearer ${newToken}`);
            return originalFetch(resource, {
                ...request,
                _retry: true,
                headers: retryHeaders,
            });
        } catch (_error) {
            clearAuthState();
            redirectToLogin();
            return response;
        }
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

    function resolveLegacyPath(path) {
        if (!path) {
            return path;
        }
        return legacyPathMap.get(path) || path;
    }

    function filterTemplateNav(items) {
        return (Array.isArray(items) ? items : []).reduce((result, item) => {
            const cloned = { ...item };
            if (cloned.path) {
                const legacyPath = resolveLegacyPath(cloned.path);
                if (!legacyPath || templateUnsupportedPaths.has(cloned.path)) {
                    return result;
                }
                cloned.path = legacyPath;
                result.push(cloned);
                return result;
            }

            if (Array.isArray(cloned.children)) {
                const children = filterTemplateNav(cloned.children);
                if (children.length) {
                    cloned.children = children;
                    result.push(cloned);
                }
            }
            return result;
        }, []);
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

    function renderSidebarMenu(items) {
        const container = document.getElementById("templateSidebarMenu");
        if (!container) {
            return;
        }

        if (!items.length) {
            container.innerHTML = '<div class="template-auth-empty-nav px-2 py-3">当前账号暂无可见菜单</div>';
            return;
        }

        container.innerHTML = items.map((item, index) => {
            if (item.path) {
                return `
                    <div>
                        <a class="nav-link ${isItemActive(item.path) ? "active" : ""}" href="${item.path}">
                            <span>${item.label}</span>
                        </a>
                    </div>
                `;
            }

            const collapseId = `templateSidebarGroup${index}`;
            const childMarkup = (item.children || []).map((child) => `
                <li>
                    <a class="nav-link ${isItemActive(child.path) ? "active" : ""}" href="${child.path}">
                        <span>${child.label}</span>
                    </a>
                </li>
            `).join("");
            const expanded = (item.children || []).some((child) => isItemActive(child.path));
            return `
                <div class="mt-3">
                    <button class="btn-toggle" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${expanded ? "true" : "false"}">
                        <span>${item.label}</span>
                        <i class="bi bi-chevron-right btn-toggle-icon"></i>
                    </button>
                    <div class="collapse ${expanded ? "show" : ""}" id="${collapseId}">
                        <ul class="btn-toggle-nav">
                            ${childMarkup}
                        </ul>
                    </div>
                </div>
            `;
        }).join("");
    }

    function renderTopMenu(items) {
        const container = document.getElementById("templateTopMenu");
        if (!container) {
            return;
        }

        const leaves = [];
        const collectLeaves = (source) => {
            (source || []).forEach((item) => {
                if (item.path) {
                    leaves.push(item);
                } else if (Array.isArray(item.children)) {
                    collectLeaves(item.children);
                }
            });
        };
        collectLeaves(items);

        const isListContainer = container.tagName === "UL" || container.tagName === "OL";

        if (!leaves.length) {
            container.innerHTML = isListContainer
                ? '<li class="nav-item"><span class="nav-link disabled">当前账号暂无可见菜单</span></li>'
                : '<span class="template-auth-empty-nav">当前账号暂无可见菜单</span>';
            return;
        }

        if (isListContainer) {
            container.innerHTML = leaves.map((item) => `
                <li class="nav-item">
                    <a class="nav-link ${isItemActive(item.path) ? "active" : ""}" href="${item.path}">${item.label}</a>
                </li>
            `).join("");
            return;
        }

        container.classList.add("template-auth-horizontal-nav");
        container.innerHTML = leaves.map((item) => `
            <a class="nav-link ${isItemActive(item.path) ? "active" : ""}" href="${item.path}">${item.label}</a>
        `).join("");
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

    async function loadNav() {
        const payload = await requestJson("/api/meta/nav", { method: "GET" });
        navItems = filterTemplateNav(payload?.data || []);
        renderSidebarMenu(navItems);
        renderTopMenu(navItems);
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
