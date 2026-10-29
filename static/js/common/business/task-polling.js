// ------------------------------
// c4/c5/c7 详情页三胞胎共享：任务轮询/日志面板/结果分页（02 §3.6，F3 收敛 pass）。
// 来源：static/js/pages/google_sheet_c{4,5,7}_detail.js（三版规范化后逐字相同，正本取自 c4）。
// 页面差异逻辑仍留在 pages 层；页面调用点经 Biz.taskPolling.* 访问。
// ------------------------------
(function () {
  window.Biz = window.Biz || {};

  function getTaskIdFromUrl() {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get("task_id");
  }

  function getFrequencyText(milliseconds) {
    const seconds = milliseconds / 1000;
    if (seconds < 60) {
      return `${seconds}秒`;
    } else {
      const minutes = seconds / 60;
      return `${minutes}分钟`;
    }
  }

  // 日志增量拉取游标：首载全量，其后每 tick 只取 after_id 之后的新增行做追加，
  // 避免任务跑数小时后每 tick 仍全量拉 500 条并整体重建 innerHTML。
  let lastTaskLogId = null;

  function renderTaskLogLine(log) {
    const level = log.level || "info";
    const levelClass =
      level === "error"
        ? "text-danger"
        : level === "warning"
          ? "text-warning"
          : level === "info"
            ? "text-info"
            : "text-light";
    // log.message 含任务参数/Sheet 标题等外部输入，进 innerHTML 前必须转义
    return `<div class="${levelClass}">[${formatTime(log.timestamp)}] ${escapeHtml(log.message)}</div>`;
  }

  function loadTaskLogs() {
    const logContainer = document.getElementById("log-container");
    const incremental = lastTaskLogId != null;
    Api.endpoints.task
      .logs(currentTaskId, incremental ? `after_id=${lastTaskLogId}` : "")
      .then(function (data) {
        if (data && data.logs) {
          if (!logContainer) {
            return;
          }
          const logs = data.logs;

          if (incremental) {
            if (logs.length === 0) {
              return;
            }
            const wasAtBottom =
              logContainer.scrollTop + logContainer.clientHeight >=
              logContainer.scrollHeight - 5;
            logContainer.insertAdjacentHTML(
              "beforeend",
              logs.map(renderTaskLogLine).join(""),
            );
            if (wasAtBottom) {
              logContainer.scrollTop = logContainer.scrollHeight;
            }
          } else if (logs.length > 0) {
            // 保存当前滚动位置
            const wasAtBottom =
              logContainer.scrollTop + logContainer.clientHeight >=
              logContainer.scrollHeight - 5;

            // 更新日志内容
            logContainer.innerHTML = logs.map(renderTaskLogLine).join("");

            // 如果之前在底部，保持滚动到底部
            if (wasAtBottom) {
              logContainer.scrollTop = logContainer.scrollHeight;
            }
          } else {
            logContainer.innerHTML = '<div class="text-muted">暂无日志</div>';
          }

          const maxId = logs.reduce(
            (acc, log) => (log.id != null && log.id > acc ? log.id : acc),
            lastTaskLogId || 0,
          );
          if (maxId > 0) {
            lastTaskLogId = maxId;
          }
        } else {
          console.error("加载日志失败:", data);
          lastTaskLogId = null;
          if (logContainer) {
            logContainer.innerHTML =
              '<div class="text-danger">加载日志失败</div>';
          }
        }
      })
      .catch(function (err) {
        console.error("加载日志失败:", err);
        // 出错即丢弃游标，下一 tick 回落全量加载自愈
        lastTaskLogId = null;
        if (logContainer) {
          logContainer.innerHTML = '<div class="text-danger">加载日志失败</div>';
        }
      });
  }

  function loadTaskResults(page) {
    const targetPage = page || currentResultsPage || 1;
    Api.endpoints.task
      .results(currentTaskId, `page=${targetPage}&per_page=${resultsPerPage}`)
      .then(function (data) {
        const rdata = data || {};
        if (data && Array.isArray(rdata.items)) {
          allResults = rdata.items;
          groupedResults = groupResults(rdata.items);
          flattenedResults = flattenResults(rdata.items);

          resultsTotalPages = rdata.pages || 1;
          resultsTotalCount =
            rdata.total != null ? rdata.total : groupedResults.length;
          resultsTotalSuccess =
            typeof rdata.total_success === "number"
              ? rdata.total_success
              : null;
          resultsTotalFailed =
            typeof rdata.total_failed === "number" ? rdata.total_failed : null;
          currentResultsPage = data.current_page || targetPage;

          applyResultsFilter();
          updateResultsStatistics();
          renderResults();
        }
      })
      .catch(function (err) {
        console.error("加载任务结果失败:", err);
      });
  }

  function changeResultsPage(page) {
    const totalPages = resultsTotalPages || 1;
    if (page >= 1 && page <= totalPages) {
      loadTaskResults(page);
    }
    // 阻止 <a href="#"> 的默认跳转，避免页面滚动到顶部
    return false;
  }

  function filterResults(filter) {
    currentResultsFilter = filter;
    currentResultsPage = 1; // 切换筛选条件时重置到第一页
    applyResultsFilter();
    renderResults();
  }

  function applyResultsFilter() {
    if (currentResultsFilter === "all") {
      filteredResults = groupedResults;
    } else if (currentResultsFilter === "success") {
      filteredResults = groupedResults.filter((result) => result.success);
    } else if (currentResultsFilter === "failed") {
      filteredResults = groupedResults.filter((result) => !result.success);
    }
  }

  function renderResultsPagination() {
    const pagination = document.getElementById("results-pagination");
    pagination.innerHTML = "";

    const totalPages = resultsTotalPages || 1;

    if (totalPages <= 1) return;

    // 上一页
    const prevLi = document.createElement("li");
    prevLi.className = `page-item ${currentResultsPage === 1 ? "disabled" : ""}`;
    prevLi.innerHTML = `<a class="page-link" href="#" onclick="return Biz.taskPolling.changeResultsPage(${currentResultsPage - 1})">上一页</a>`;
    pagination.appendChild(prevLi);

    // 页码
    const startPage = Math.max(1, currentResultsPage - 2);
    const endPage = Math.min(totalPages, currentResultsPage + 2);

    for (let i = startPage; i <= endPage; i++) {
      const li = document.createElement("li");
      li.className = `page-item ${i === currentResultsPage ? "active" : ""}`;
      li.innerHTML = `<a class="page-link" href="#" onclick="return Biz.taskPolling.changeResultsPage(${i})">${i}</a>`;
      pagination.appendChild(li);
    }

    // 下一页
    const nextLi = document.createElement("li");
    nextLi.className = `page-item ${currentResultsPage === totalPages ? "disabled" : ""}`;
    nextLi.innerHTML = `<a class="page-link" href="#" onclick="return Biz.taskPolling.changeResultsPage(${currentResultsPage + 1})">下一页</a>`;
    pagination.appendChild(nextLi);
  }

  function isPlainObject(value) {
    return value != null && typeof value === "object" && !Array.isArray(value);
  }

  function getFlatResult(metrics) {
    if (!isPlainObject(metrics)) {
      return null;
    }

    const payload = metrics.metrics_payload;
    return isPlainObject(payload) && isPlainObject(payload.metrics)
      ? payload.metrics
      : null;
  }

  function getPreferredMetricValue(metrics, key) {
    const flatResult = getFlatResult(metrics);
    if (flatResult && flatResult[key] != null) {
      return flatResult[key];
    }
    return metrics && metrics[key] != null ? metrics[key] : null;
  }

  function getFirstMetricValue(source, keys) {
    if (!isPlainObject(source)) {
      return null;
    }

    for (const key of keys) {
      if (source[key] != null) {
        return source[key];
      }
    }
    return null;
  }

  function getModelSharpeValue(metrics, type) {
    const flatResult = getFlatResult(metrics);
    if (flatResult) {
      const ratios = flatResult[type + "_sharpe_ratios"];
      const allEntry = isPlainObject(ratios) ? ratios.all : null;
      return isPlainObject(allEntry) && allEntry.sharpe_ratio != null
        ? allEntry.sharpe_ratio
        : null;
    }
    return null;
  }

  function getDetailMetricSource(metrics) {
    return isPlainObject(metrics) ? metrics : {};
  }

  function shouldShowDetailMetric(key) {
    return key !== "metrics_payload";
  }

  // ------------------------------
  // 「更多」结果详情弹窗共享渲染（c1_1/c4/c5/c7 + C3 详情页统一格式）。
  // 页面只负责取数、指标 label 与数值格式化；meta 卡片、收益分析卡片、
  // 指标网格的拼装统一在这里，避免五个页面各写一份导致格式漂移。
  // ------------------------------

  // meta 信息卡片网格。items: [{label, value}] 或 [{label, html}]（html 用于徽章等富文本，调用方保证已转义）。
  function renderResultDetailMeta(items) {
    const chips = (Array.isArray(items) ? items : [])
      .filter((item) => item && item.label != null)
      .map((item) => {
        const valueHtml =
          item.html != null
            ? item.html
            : `<span>${escapeHtml(item.value == null || item.value === "" ? "-" : String(item.value))}</span>`;
        const titleAttr =
          item.value == null ? "" : ` title="${escapeHtml(String(item.value))}"`;
        return `
          <div class="col-6 col-md-4 col-xl-2">
            <div class="border rounded p-1 px-2 h-100">
              <div class="text-muted" style="font-size: 0.75rem;">${escapeHtml(item.label)}</div>
              <div class="fw-semibold small text-break"${titleAttr}>${valueHtml}</div>
            </div>
          </div>`;
      });
    if (chips.length === 0) {
      return "";
    }
    return `<div class="row g-2">${chips.join("")}</div>`;
  }

  // 模型/指数收益分析卡片（start_return_xpl / index_return_xpl 字典 → 7 行固定字段）。
  // formatFloat：页面传入的数值格式化回调（如 formatMetricRawValue(v, 6)），返回 null 时显示「-」。
  function renderReturnAnalysisCard(title, data, formatFloat) {
    if (!isPlainObject(data)) {
      return "";
    }
    const format = typeof formatFloat === "function" ? formatFloat : (v) => v;
    const line = (label, value) => {
      const text = value == null || value === "" ? null : String(value);
      const display =
        text == null
          ? '<span class="text-muted">-</span>'
          : escapeHtml(text);
      const titleAttr = text == null ? "" : ` title="${escapeHtml(text)}"`;
      return `
        <div class="d-flex justify-content-between gap-2 border-bottom py-1">
          <span class="text-muted flex-shrink-0">${escapeHtml(label)}</span>
          <span class="text-end text-truncate"${titleAttr}>${display}</span>
        </div>`;
    };

    return `
      <div class="col-12 col-md-6">
        <div class="card h-100">
          <div class="card-header py-1 px-2 small fw-semibold">${escapeHtml(title)}</div>
          <div class="card-body py-1 px-2 small">
            ${line("起始日期", data.start_date)}
            ${line("结束日期", data.end_date)}
            ${line("月份数", data.month_count)}
            ${line("平均月收益", format(data.avg_monthly_return))}
            ${line("月度波动率", format(data.monthly_std_dev))}
            ${line("年化波动率", format(data.annual_std_dev))}
            ${line("夏普率", format(data.sharpe_ratio))}
          </div>
        </div>
      </div>`;
  }

  // 弹窗主体：收益分析卡片行 + 指标网格。entries: [{label, html, wide?}]，
  // label/html 由页面用各自的映射表渲染好传入；wide 用于数组/嵌套对象等长内容独占一行。
  function renderResultDetailBody(options) {
    const opts = isPlainObject(options) ? options : {};
    const cards = Array.isArray(opts.cards) ? opts.cards.filter(Boolean) : [];
    const entries = Array.isArray(opts.entries) ? opts.entries.filter(Boolean) : [];

    const cardsHtml =
      cards.length > 0 ? `<div class="row g-2 mb-3">${cards.join("")}</div>` : "";

    const itemsHtml = entries
      .map((entry) => {
        if (entry.wide) {
          return `
            <div class="col-12">
              <div class="border rounded px-2 py-1 small">
                <div class="text-muted">${entry.label}</div>
                <div class="mt-1">${entry.html}</div>
              </div>
            </div>`;
        }
        return `
          <div class="col-12 col-md-6">
            <div class="d-flex justify-content-between align-items-center gap-2 border rounded px-2 py-1 h-100 small">
              <span class="text-muted flex-shrink-0">${entry.label}</span>
              <span class="text-end" style="min-width: 0;">${entry.html}</span>
            </div>
          </div>`;
      })
      .join("");

    if (cardsHtml === "" && itemsHtml === "") {
      return `<div class="text-muted text-center small py-3">${escapeHtml(opts.emptyText || "无详细指标")}</div>`;
    }
    return cardsHtml + (itemsHtml ? `<div class="row g-2">${itemsHtml}</div>` : "");
  }

  Biz.taskPolling = {
    getTaskIdFromUrl: getTaskIdFromUrl,
    getFrequencyText: getFrequencyText,
    loadTaskLogs: loadTaskLogs,
    loadTaskResults: loadTaskResults,
    changeResultsPage: changeResultsPage,
    filterResults: filterResults,
    applyResultsFilter: applyResultsFilter,
    renderResultsPagination: renderResultsPagination,
    isPlainObject: isPlainObject,
    getFlatResult: getFlatResult,
    getPreferredMetricValue: getPreferredMetricValue,
    getFirstMetricValue: getFirstMetricValue,
    getModelSharpeValue: getModelSharpeValue,
    getDetailMetricSource: getDetailMetricSource,
    shouldShowDetailMetric: shouldShowDetailMetric,
    renderResultDetailMeta: renderResultDetailMeta,
    renderReturnAnalysisCard: renderReturnAnalysisCard,
    renderResultDetailBody: renderResultDetailBody,
  };
})();
