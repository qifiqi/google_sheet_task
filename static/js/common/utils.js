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
