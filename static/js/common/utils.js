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
    c1_1: "C1.1",
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
// 会产生 "12026-01-01" 这类离谱日期并流入任务参数。这里统一给日期输入补 min/max，
// 并在 change 时拦截越界值（清空 + 标红提示）。utils.js 被全部页面引入，此处即全局生效。
// 注意越界判断不能用字符串比较：'202664-06-04' 按字典序小于 '2099-12-31'，必须按年份数值判。
const DATE_GUARD_MIN_YEAR = 1990;
const DATE_GUARD_MAX_YEAR = 2099;
const DATE_GUARD_VALID_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

function initDateInputGuards(root) {
  const scope = root || document;
  scope.querySelectorAll('input[type="date"]').forEach((input) => {
    if (input.dataset.dateGuardInit) {
      return;
    }
    input.dataset.dateGuardInit = "1";
    if (!input.getAttribute("min")) {
      input.setAttribute("min", `${DATE_GUARD_MIN_YEAR}-01-01`);
    }
    if (!input.getAttribute("max")) {
      input.setAttribute("max", `${DATE_GUARD_MAX_YEAR}-12-31`);
    }
    input.addEventListener("change", function () {
      const value = input.value;
      if (!value) {
        return;
      }
      const match = value.match(DATE_GUARD_VALID_RE);
      const year = match ? Number(match[1]) : NaN;
      if (!match || Number.isNaN(year) || year < DATE_GUARD_MIN_YEAR || year > DATE_GUARD_MAX_YEAR) {
        input.value = "";
        input.classList.add("is-invalid");
        setTimeout(() => input.classList.remove("is-invalid"), 2500);
        const message = `日期 ${value} 超出有效范围（${DATE_GUARD_MIN_YEAR}-01-01 ~ ${DATE_GUARD_MAX_YEAR}-12-31），已清空，请重新选择`;
        if (typeof showNotification === "function") {
          showNotification(message, "warning");
        } else {
          console.warn(message);
        }
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
