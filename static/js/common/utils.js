// 跨页共享纯工具函数（docs/design/frontend-refactor/02 §1）。
// 以 google_sheet/base.html 内联脚本为基准收敛，同名同签名，调用点零修改。
// 引入顺序：template-auth.js → navbar.js → api.js → utils.js → 页面 JS。
"use strict";

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function parseJsonArray(text) {
  try {
    if (!String(text || "").trim()) {
      return [];
    }
    return JSON.parse(text);
  } catch (e) {
    return null;
  }
}

function extractSpreadsheetId(url) {
  const regex = /\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/;
  const match = String(url || "").match(regex);
  if (match && match[1]) {
    return match[1];
  }
  return url;
}

function formatModelVersion(value) {
  const raw = String(value || "").trim().toLowerCase().replace(/[-.]/g, "_");
  const labels = {
    c3: "C3",
    c4: "C4",
    c5: "C5",
    c7_0_2: "C7.0.2",
    c7_0_3: "C7.0.3",
    c1_1: "C1.1.0",
  };
  return labels[raw] || String(value || "").trim().toUpperCase();
}

// 统一导出文件名规范（与后端 build_export_filename 对偶）：
// {基名}-{模型版本}-{K线起}-{K线止}-{导出时间}.{扩展名}
// 段间 `-`、段内 `_`；模型版本/区间缺失时整段省略，导出时间恒在。
function normalizeExportFilenameDate(value) {
  const head = String(value || "").trim().split(/[ T]/)[0];
  const match = head.match(/^(\d{4})[-/]?(\d{1,2})[-/]?(\d{1,2})$/);
  if (!match) return "";
  const pad = (part) => part.padStart(2, "0");
  return `${match[1]}${pad(match[2])}${pad(match[3])}`;
}

function buildExportFilename(base, options) {
  const opts = options || {};
  const pad = (num) => String(num).padStart(2, "0");
  const now = new Date();
  const stamp = (
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
    + `_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  );
  let start = normalizeExportFilenameDate(opts.klineStart);
  let end = normalizeExportFilenameDate(opts.klineEnd);
  if (start && end && start > end) [start, end] = [end, start];
  if (!(start && end)) {
    start = "";
    end = "";
  }
  const segments = [
    String(base || "").replace(/[\\/:*?"<>|]/g, "_").trim(),
    String(opts.modelVersion || "").trim(),
    start,
    end,
    stamp,
  ];
  let name = segments.filter(Boolean).join("-");
  if (name.length > 180) {
    const overflow = name.length - 180;
    const keptBase = segments[0].slice(0, Math.max(segments[0].length - overflow, 1)).replace(/[-_ .]+$/, "");
    name = [keptBase, ...segments.slice(1).filter(Boolean)].join("-");
  }
  return `${name}.${opts.extension || "xlsx"}`;
}

// 从绩效分析指标里取真实 K 线区间（excess_returns 的 all 行 start_end_date = "起/止"）。
function extractKlineRangeFromMetrics(metrics) {
  const rows = metrics && Array.isArray(metrics.excess_returns) ? metrics.excess_returns : [];
  const allRow = rows.find((row) => String(row && row.year).toLowerCase() === "all")
    || rows[rows.length - 1]
    || {};
  const parts = String(allRow.start_end_date || "").split("/");
  return { start: parts[0] || "", end: parts[1] || "" };
}

// —— 全局日期输入约束 ——
// 原生 <input type="date"> 的年份段允许连续输入 5~6 位数字（HTML 规范年份上限 275760），
// 会产生 "12026-01-01" 这类离谱日期并流入任务参数。这里只在 input 时把超过 4 位的年份
// 截断回前 4 位（Chrome 年份段是逐位左移累加，第 5 位起才是多敲的），其余一律放行：
// 不做年份区间校验，不清空、不提示，输入过程中的中间态（如改年份时先变成 "0020"）不受干扰。
// 注意截断不能等 change：Chrome 在改出完整日期的瞬间就触发 change（不等失焦），
// 在 change 里校验会把打字打到一半的中间态当成越界值误清空。
const DATE_GUARD_LONG_YEAR_RE = /^(\d{4,})-(\d{2})-(\d{2})$/;

function initDateInputGuards(root) {
  const scope = root || document;
  scope.querySelectorAll('input[type="date"]').forEach((input) => {
    if (input.dataset.dateGuardInit) {
      return;
    }
    input.dataset.dateGuardInit = "1";
    input.addEventListener("input", function () {
      const value = input.value;
      if (!value) {
        return;
      }
      const match = value.match(DATE_GUARD_LONG_YEAR_RE);
      if (match && match[1].length > 4) {
        input.value = `${match[1].slice(0, 4)}-${match[2]}-${match[3]}`;
      }
    });
  });
}

(function initDateGuardsOnLoad() {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initDateInputGuards();
    });
  } else {
    // utils.js 统一在各页 </body> 前引入，DOM 已就绪
    initDateInputGuards();
  }
})();

// 按钮加载态：spinner + 文案 + 禁用三合一。导出/生成类操作等待普遍在数秒到
// 数十秒，统一的可见 loading 反馈用于抑制"按了没反应"引发的重复点击。
// busy=true 进入加载态（保存原 innerHTML 与 disabled，重复调用防重入）；
// busy=false 恢复进入前状态；调用方需要自定义终态禁用时在恢复后另行赋值。
function setButtonBusy(button, busy, busyText) {
  if (!button) {
    return;
  }
  if (busy) {
    if (button.dataset.busyHtml !== undefined) {
      return;
    }
    button.dataset.busyHtml = button.innerHTML;
    button.dataset.busyDisabled = button.disabled ? "1" : "0";
    button.disabled = true;
    button.innerHTML =
      '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>' +
      (busyText || "导出中…");
  } else {
    if (button.dataset.busyHtml === undefined) {
      return;
    }
    button.innerHTML = button.dataset.busyHtml;
    button.disabled = button.dataset.busyDisabled === "1";
    delete button.dataset.busyHtml;
    delete button.dataset.busyDisabled;
  }
}

// 仅在页面可见时运行的 setInterval：后台标签页挂起轮询，回到前台立即补拉一次。
// 本平台任务常跑数小时，后台标签若照常轮询，服务端 QPS 与打开标签数成正比。
// 返回停止函数（清定时器并解绑 visibilitychange）。
function setIntervalVisible(fn, delay) {
  let paused = document.hidden;
  const timer = setInterval(function () {
    if (!paused) {
      fn();
    }
  }, delay);
  function handleVisibilityChange() {
    const wasPaused = paused;
    paused = document.hidden;
    if (wasPaused && !paused) {
      fn();
    }
  }
  document.addEventListener("visibilitychange", handleVisibilityChange);
  return function stopIntervalVisible() {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  };
}
