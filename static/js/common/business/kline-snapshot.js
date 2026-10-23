// ------------------------------
// C1.1/C5/C7 详情页共享：随机K线快照查看弹窗与 CSV 下载。
// 接口经 common/api.js，鉴权由 template-auth.js 的 fetch 拦截。
// ------------------------------
(function () {
  window.Biz = window.Biz || {};

  const PAGE_SIZE = 20;
  const PREVIEW_ROWS = 200;

  const state = {
    taskId: null,
    page: 1,
    pages: 0,
    total: 0,
    stockCode: "",
    randomGroup: "",
    seriesId: null,
  };

  let modalInstance = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatTime(value) {
    if (!value) {
      return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return escapeHtml(value);
    }
    return date.toLocaleString();
  }

  function formatValue(value) {
    return value == null ? "" : String(value);
  }

  function filenameFromResponse(response, fallback) {
    const disposition = response.headers.get("Content-Disposition") || "";
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (!encoded) {
      return fallback;
    }
    try {
      return decodeURIComponent(encoded[1]);
    } catch (_error) {
      return fallback;
    }
  }

  async function download(response, fallback) {
    if (!response.ok) {
      const text = await response.text();
      let message = `下载失败，状态码 ${response.status}`;
      if (text) {
        try {
          message = JSON.parse(text).message || message;
        } catch (_error) {
          message = text;
        }
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filenameFromResponse(response, fallback);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  async function runDownload(request, fallback) {
    try {
      await download(await request(), fallback);
      showNotification("随机K线已开始下载", "success");
    } catch (error) {
      showNotification(
        `下载随机K线失败: ${error && error.message ? error.message : error}`,
        "error",
      );
    }
  }

  function ensureModal() {
    if (modalInstance) {
      return modalInstance;
    }
    if (typeof bootstrap === "undefined" || !bootstrap.Modal) {
      showNotification("页面未加载 Bootstrap，无法打开随机K线弹窗", "error");
      return null;
    }

    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <div class="modal fade" id="kline-snapshot-modal" tabindex="-1" aria-labelledby="kline-snapshot-modal-label" aria-hidden="true">
        <div class="modal-dialog modal-xl modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="kline-snapshot-modal-label">随机K线快照</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
            </div>
            <div class="modal-body">
              <div id="kline-snapshot-list-view">
                <div class="row g-2 align-items-end mb-3">
                  <div class="col-sm-4">
                    <label class="form-label small mb-1" for="kline-snapshot-stock-code">股票代码</label>
                    <input id="kline-snapshot-stock-code" class="form-control form-control-sm" placeholder="精确匹配，如 600000">
                  </div>
                  <div class="col-sm-3">
                    <label class="form-label small mb-1" for="kline-snapshot-random-group">随机组号</label>
                    <input id="kline-snapshot-random-group" type="number" min="1" class="form-control form-control-sm" placeholder="如 1">
                  </div>
                  <div class="col-sm-5 d-flex gap-2">
                    <button type="button" class="btn btn-primary btn-sm" data-kline-action="search">查询</button>
                    <button type="button" class="btn btn-outline-secondary btn-sm" data-kline-action="reset">重置</button>
                  </div>
                </div>
                <div id="kline-snapshot-list-summary" class="small text-muted mb-2"></div>
                <div class="table-responsive">
                  <table class="table table-sm table-hover align-middle mb-0">
                    <thead class="table-light">
                      <tr>
                        <th>股票</th>
                        <th>K线窗口</th>
                        <th>组号</th>
                        <th>价格区间</th>
                        <th>行数</th>
                        <th>创建时间</th>
                        <th class="text-end">操作</th>
                      </tr>
                    </thead>
                    <tbody id="kline-snapshot-list-body"></tbody>
                  </table>
                </div>
                <div class="d-flex justify-content-between align-items-center mt-3">
                  <div id="kline-snapshot-page-info" class="small text-muted"></div>
                  <div class="btn-group btn-group-sm">
                    <button type="button" class="btn btn-outline-secondary" data-kline-action="prev">上一页</button>
                    <button type="button" class="btn btn-outline-secondary" data-kline-action="next">下一页</button>
                  </div>
                </div>
                <div id="kline-snapshot-list-error" class="alert alert-danger mt-3 d-none" role="alert"></div>
              </div>
              <div id="kline-snapshot-detail-view" class="d-none">
                <div class="d-flex justify-content-between align-items-center mb-2">
                  <button type="button" class="btn btn-outline-secondary btn-sm" data-kline-action="back">返回列表</button>
                  <button type="button" class="btn btn-outline-success btn-sm" data-kline-action="download-series">下载 CSV</button>
                </div>
                <div id="kline-snapshot-detail-meta" class="small mb-3"></div>
                <div id="kline-snapshot-detail-note" class="small text-muted mb-2"></div>
                <div class="table-responsive">
                  <table class="table table-sm table-bordered align-middle mb-0">
                    <thead class="table-light">
                      <tr>
                        <th>日期</th>
                        <th>随机价</th>
                        <th>Open</th>
                        <th>High</th>
                        <th>Low</th>
                        <th>Close</th>
                        <th>VWAP</th>
                      </tr>
                    </thead>
                    <tbody id="kline-snapshot-detail-body"></tbody>
                  </table>
                </div>
                <div id="kline-snapshot-detail-error" class="alert alert-danger mt-3 d-none" role="alert"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    const modalEl = wrapper.firstElementChild;
    document.body.appendChild(modalEl);

    modalEl.addEventListener("click", handleModalClick);
    ["kline-snapshot-stock-code", "kline-snapshot-random-group"].forEach(
      function (id) {
        const input = document.getElementById(id);
        if (!input) {
          return;
        }
        input.addEventListener("keydown", function (event) {
          if (event.key === "Enter") {
            event.preventDefault();
            state.page = 1;
            loadList();
          }
        });
      },
    );

    const Modal = bootstrap.Modal;
    modalInstance = Modal.getOrCreateInstance
      ? Modal.getOrCreateInstance(modalEl)
      : new Modal(modalEl);
    return modalInstance;
  }

  function handleModalClick(event) {
    const target = event.target.closest("[data-kline-action]");
    if (!target) {
      return;
    }
    const action = target.getAttribute("data-kline-action");
    if (action === "search") {
      state.page = 1;
      loadList();
    } else if (action === "reset") {
      document.getElementById("kline-snapshot-stock-code").value = "";
      document.getElementById("kline-snapshot-random-group").value = "";
      state.stockCode = "";
      state.randomGroup = "";
      state.page = 1;
      loadList();
    } else if (action === "prev") {
      if (state.page > 1) {
        state.page -= 1;
        loadList();
      }
    } else if (action === "next") {
      if (state.page < state.pages) {
        state.page += 1;
        loadList();
      }
    } else if (action === "view") {
      const seriesId = Number(target.getAttribute("data-series-id"));
      if (seriesId) {
        openSeries(state.taskId, seriesId);
      }
    } else if (action === "download") {
      const seriesId = Number(target.getAttribute("data-series-id"));
      if (seriesId) {
        downloadSeries(state.taskId, seriesId);
      }
    } else if (action === "back") {
      showListView();
      loadList();
    } else if (action === "download-series") {
      if (state.seriesId) {
        downloadSeries(state.taskId, state.seriesId);
      }
    }
  }

  function readFilters() {
    const stockInput = document.getElementById("kline-snapshot-stock-code");
    const groupInput = document.getElementById("kline-snapshot-random-group");
    state.stockCode = stockInput ? stockInput.value.trim() : "";
    const groupValue = groupInput ? groupInput.value.trim() : "";
    state.randomGroup = groupValue
      ? String(Math.max(1, Number(groupValue) || 1))
      : "";
  }

  function buildListQuery() {
    const params = new URLSearchParams();
    params.set("page", String(state.page));
    params.set("per_page", String(PAGE_SIZE));
    if (state.stockCode) {
      params.set("stock_code", state.stockCode);
    }
    if (state.randomGroup) {
      params.set("random_group", state.randomGroup);
    }
    return params.toString();
  }

  async function loadList() {
    readFilters();
    const listError = document.getElementById("kline-snapshot-list-error");
    const tbody = document.getElementById("kline-snapshot-list-body");
    const summary = document.getElementById("kline-snapshot-list-summary");
    if (!tbody || !state.taskId) {
      return;
    }
    listError.classList.add("d-none");
    tbody.innerHTML =
      '<tr><td colspan="7" class="text-center text-muted py-3">加载中...</td></tr>';
    try {
      const data = await Api.endpoints.task.klineSnapshots(
        state.taskId,
        buildListQuery(),
      );
      const items = (data && data.items) || [];
      state.total = (data && data.total) || 0;
      state.pages = (data && data.pages) || 0;
      state.page = (data && data.current_page) || state.page;
      summary.textContent = `共 ${state.total} 组随机K线快照`;
      renderList(items);
      renderPagination();
    } catch (error) {
      tbody.innerHTML = "";
      listError.textContent = `加载随机K线快照失败: ${
        error && error.message ? error.message : error
      }`;
      listError.classList.remove("d-none");
      summary.textContent = "";
      renderPagination();
    }
  }

  function renderList(items) {
    const tbody = document.getElementById("kline-snapshot-list-body");
    if (!items.length) {
      tbody.innerHTML =
        '<tr><td colspan="7" class="text-center text-muted py-3">暂无随机K线快照</td></tr>';
      return;
    }
    tbody.innerHTML = items
      .map(function (item) {
        const stock = escapeHtml(item.stock_code || "-");
        const stockName = item.stock_name
          ? `<div class="small text-muted">${escapeHtml(item.stock_name)}</div>`
          : "";
        const windowText = escapeHtml(item.kline_key || "-");
        const dateRange = [item.start_date, item.end_date]
          .filter(Boolean)
          .map(escapeHtml)
          .join(" ~ ");
        const group = escapeHtml(
          item.random_group == null ? "-" : item.random_group,
        );
        const priceRange = escapeHtml(item.random_price_range || "-");
        const rowCount = escapeHtml(
          item.row_count == null ? "-" : item.row_count,
        );
        const createdAt = formatTime(item.created_at);
        return `
          <tr>
            <td>${stock}${stockName}</td>
            <td>${windowText}${dateRange ? `<div class="small text-muted">${dateRange}</div>` : ""}</td>
            <td>${group}</td>
            <td>${priceRange}</td>
            <td>${rowCount}</td>
            <td>${createdAt}</td>
            <td class="text-end">
              <button type="button" class="btn btn-link btn-sm p-0 me-2" data-kline-action="view" data-series-id="${escapeHtml(item.id)}">查看</button>
              <button type="button" class="btn btn-link btn-sm p-0" data-kline-action="download" data-series-id="${escapeHtml(item.id)}">下载</button>
            </td>
          </tr>`;
      })
      .join("");
  }

  function renderPagination() {
    const info = document.getElementById("kline-snapshot-page-info");
    const prev = document.querySelector('[data-kline-action="prev"]');
    const next = document.querySelector('[data-kline-action="next"]');
    if (!info) {
      return;
    }
    info.textContent =
      state.pages > 0 ? `第 ${state.page} / ${state.pages} 页` : "";
    if (prev) {
      prev.disabled = state.page <= 1;
    }
    if (next) {
      next.disabled = state.pages === 0 || state.page >= state.pages;
    }
  }

  function showListView() {
    document.getElementById("kline-snapshot-list-view").classList.remove("d-none");
    document.getElementById("kline-snapshot-detail-view").classList.add("d-none");
  }

  function showDetailView() {
    document.getElementById("kline-snapshot-list-view").classList.add("d-none");
    document.getElementById("kline-snapshot-detail-view").classList.remove("d-none");
  }

  async function loadDetail(seriesId) {
    const meta = document.getElementById("kline-snapshot-detail-meta");
    const note = document.getElementById("kline-snapshot-detail-note");
    const tbody = document.getElementById("kline-snapshot-detail-body");
    const errorEl = document.getElementById("kline-snapshot-detail-error");
    errorEl.classList.add("d-none");
    meta.innerHTML = "加载中...";
    note.textContent = "";
    tbody.innerHTML = "";
    try {
      const data = await Api.endpoints.task.klineSnapshot(
        state.taskId,
        seriesId,
      );
      const series = (data && data.series) || {};
      const source = (data && data.source) || {};
      const rows = (data && data.rows) || [];
      state.seriesId = seriesId;
      meta.innerHTML = `
        <div class="row g-2">
          <div class="col-md-4"><span class="text-muted">股票：</span>${escapeHtml(series.stock_code || "-")} ${escapeHtml(source.stock_name || "")}</div>
          <div class="col-md-4"><span class="text-muted">K线窗口：</span>${escapeHtml(series.kline_key || "-")}（${escapeHtml(source.start_date || "-")} ~ ${escapeHtml(source.end_date || "-")}）</div>
          <div class="col-md-4"><span class="text-muted">随机组：</span>${escapeHtml(series.random_group == null ? "-" : series.random_group)} · ${escapeHtml(series.random_price_range || "-")}</div>
          <div class="col-md-4"><span class="text-muted">数据源：</span>${escapeHtml(source.data_source || "-")}</div>
          <div class="col-md-4"><span class="text-muted">复权：</span>${escapeHtml(source.adjust_type || "-")}</div>
          <div class="col-md-4"><span class="text-muted">行数：</span>${escapeHtml(rows.length)}</div>
        </div>`;
      note.textContent =
        rows.length > PREVIEW_ROWS
          ? `仅展示前 ${PREVIEW_ROWS} 行（共 ${rows.length} 行），下载 CSV 查看全部。`
          : "";
      tbody.innerHTML = rows
        .slice(0, PREVIEW_ROWS)
        .map(function (row) {
          return `
            <tr>
              <td>${escapeHtml(row.stock_date || "")}</td>
              <td>${escapeHtml(formatValue(row.stock_val))}</td>
              <td>${escapeHtml(formatValue(row.open))}</td>
              <td>${escapeHtml(formatValue(row.high))}</td>
              <td>${escapeHtml(formatValue(row.low))}</td>
              <td>${escapeHtml(formatValue(row.close))}</td>
              <td>${escapeHtml(formatValue(row.vwap))}</td>
            </tr>`;
        })
        .join("");
    } catch (error) {
      meta.innerHTML = "";
      errorEl.textContent = `加载快照详情失败: ${
        error && error.message ? error.message : error
      }`;
      errorEl.classList.remove("d-none");
    }
  }

  function openBrowser(taskId) {
    if (!taskId) {
      showNotification("任务ID为空，无法查看随机K线", "error");
      return;
    }
    const modal = ensureModal();
    if (!modal) {
      return;
    }
    state.taskId = taskId;
    state.page = 1;
    state.pages = 0;
    state.total = 0;
    state.stockCode = "";
    state.randomGroup = "";
    state.seriesId = null;
    const stockInput = document.getElementById("kline-snapshot-stock-code");
    const groupInput = document.getElementById("kline-snapshot-random-group");
    if (stockInput) {
      stockInput.value = "";
    }
    if (groupInput) {
      groupInput.value = "";
    }
    showListView();
    modal.show();
    loadList();
  }

  function openSeries(taskId, seriesId) {
    if (!taskId) {
      showNotification("任务ID为空，无法查看随机K线", "error");
      return;
    }
    const modal = ensureModal();
    if (!modal) {
      return;
    }
    state.taskId = taskId;
    state.seriesId = seriesId;
    showDetailView();
    modal.show();
    loadDetail(seriesId);
  }

  function downloadTask(taskId) {
    return runDownload(
      function () {
        return Api.endpoints.export.taskKlineSnapshots(taskId);
      },
      `task-${taskId}-kline-snapshots.csv`,
    );
  }

  function downloadSeries(taskId, seriesId) {
    return runDownload(
      function () {
        return Api.endpoints.export.seriesKlineSnapshot(taskId, seriesId);
      },
      `task-${taskId}-kline-${seriesId}.csv`,
    );
  }

  Biz.klineSnapshot = {
    openBrowser: openBrowser,
    openSeries: openSeries,
    downloadTask: downloadTask,
    downloadSeries: downloadSeries,
  };
})();
