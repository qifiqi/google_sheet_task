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

  function loadTaskLogs() {
    console.log("开始加载任务日志...");
    Api.endpoints.task
      .logs(currentTaskId)
      .then(function (data) {
        console.log("日志API响应:", data);
        if (data && data.logs) {
          const logContainer = document.getElementById("log-container");
          console.log("找到日志容器:", logContainer);
          console.log("日志数量:", data.logs.length);

          if (data.logs.length > 0) {
            // 保存当前滚动位置
            const wasAtBottom =
              logContainer.scrollTop + logContainer.clientHeight >=
              logContainer.scrollHeight - 5;

            // 更新日志内容
            logContainer.innerHTML = data.logs
              .map((log) => {
                const level = log.level || "info";
                const levelClass =
                  level === "error"
                    ? "text-danger"
                    : level === "warning"
                      ? "text-warning"
                      : level === "info"
                        ? "text-info"
                        : "text-light";
                return `<div class="${levelClass}">[${formatTime(log.timestamp)}] ${log.message}</div>`;
              })
              .join("");

            // 如果之前在底部，保持滚动到底部
            if (wasAtBottom) {
              logContainer.scrollTop = logContainer.scrollHeight;
            }

            console.log("日志已显示");
          } else {
            logContainer.innerHTML = '<div class="text-muted">暂无日志</div>';
            console.log("没有日志数据");
          }
        } else {
          console.error("加载日志失败:", data);
          const logContainer = document.getElementById("log-container");
          logContainer.innerHTML =
            '<div class="text-danger">加载日志失败</div>';
        }
      })
      .catch(function (err) {
        console.error("加载日志失败:", err);
        const logContainer = document.getElementById("log-container");
        logContainer.innerHTML = '<div class="text-danger">加载日志失败</div>';
      });
  }

  function loadTaskResults(page) {
    const targetPage = page || 1;
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
    prevLi.innerHTML = `<a class="page-link" href="#" onclick="return changeResultsPage(${currentResultsPage - 1})">上一页</a>`;
    pagination.appendChild(prevLi);

    // 页码
    const startPage = Math.max(1, currentResultsPage - 2);
    const endPage = Math.min(totalPages, currentResultsPage + 2);

    for (let i = startPage; i <= endPage; i++) {
      const li = document.createElement("li");
      li.className = `page-item ${i === currentResultsPage ? "active" : ""}`;
      li.innerHTML = `<a class="page-link" href="#" onclick="return changeResultsPage(${i})">${i}</a>`;
      pagination.appendChild(li);
    }

    // 下一页
    const nextLi = document.createElement("li");
    nextLi.className = `page-item ${currentResultsPage === totalPages ? "disabled" : ""}`;
    nextLi.innerHTML = `<a class="page-link" href="#" onclick="return changeResultsPage(${currentResultsPage + 1})">下一页</a>`;
    pagination.appendChild(nextLi);
  }

  function isPlainObject(value) {
    return value != null && typeof value === "object" && !Array.isArray(value);
  }

  function getFlatResult(metrics) {
    if (!isPlainObject(metrics)) {
      return null;
    }

    return isPlainObject(metrics.flat_result) ? metrics.flat_result : null;
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
      if (type === "index") {
        return getFirstMetricValue(flatResult, [
          "index_sharpe_ratio",
          "index_sharp",
          "ixpl",
          "i_xpl",
          "index_xpl",
        ]);
      }
      return getFirstMetricValue(flatResult, [
        "start_sharpe_ratio",
        "start_sharp",
        "sxpl",
        "s_xpl",
        "start_xpl",
      ]);
    }

    const legacyPerformanceAnalysis =
      type === "index"
        ? metrics.index_return_xpl || {}
        : metrics.start_return_xpl || {};
    return legacyPerformanceAnalysis.sharpe_ratio != null
      ? legacyPerformanceAnalysis.sharpe_ratio
      : null;
  }

  function getDetailMetricSource(metrics) {
    return isPlainObject(metrics) ? metrics : {};
  }

  function shouldShowDetailMetric(key) {
    return !["start_return_xpl", "index_return_xpl", "analyze_result"].includes(
      String(key),
    );
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
  };
})();
