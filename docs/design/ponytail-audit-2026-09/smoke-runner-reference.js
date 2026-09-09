// 页面冒烟场景差分脚本（ponytail-audit P11 子批1 配套工具，2026-09-09）
// 用法：
//   1. 启动冒烟服务： DATABASE_URL="sqlite:///instance/smoke.db" python run_smoke.py
//      （需先 flask init-db + 编程创建用户；run_smoke.py 跳过 bootstrap_app）
//   2. 浏览器登录后，在创建页上下文执行 INJECT_FN（拦截 /api/tasks POST 与
//      /api/google-sheet/sheets、/api/google-sheet-tokens GET）。
//   3. SCENARIO_FN(scn) 注入确定性状态并点击提交；captured[0].body 即提交 payload。
//   4. 重构前后各跑一轮（s1/s2_custom/s3_random/s4_nplus1），剔除 name（含时间戳）
//      后逐字段 diff，必须完全一致。
// 本文件为参考实现存档；实际差分通过浏览器 evaluate 执行（见 02 文档 §4 P11 子批1）。

const INJECT_SOURCE = `
window.__capturedPayloads = [];
const FAKE_SHEETS = JSON.stringify({
  status: "success", code: 0, message: "ok",
  data: { items: [{ id: "1", spreadsheet_id: "smoke-sheet-1", name: "Smoke Sheet 1" }] }
});
const FAKE_TOKENS = JSON.stringify({
  status: "success", code: 0, message: "ok",
  data: { items: [{ id: "smoke-token-1", name: "Smoke Token", token_type: "json", is_active: true }] }
});
const realFetch = window.fetch;
window.fetch = function (input, init) {
  const url = typeof input === "string" ? input : (input && input.url) || "";
  const method = ((init && init.method) || "GET").toUpperCase();
  if (method === "POST" && url.includes("/api/tasks")) {
    window.__capturedPayloads.push({ url, body: (init && init.body) || null });
    return Promise.resolve(new Response(JSON.stringify(
      { status: "error", code: 1, message: "SMOKE_CAPTURE", data: null }
    ), { status: 200, headers: { "Content-Type": "application/json" } }));
  }
  if (method === "GET" && url.includes("/api/google-sheet/sheets")) {
    return Promise.resolve(new Response(FAKE_SHEETS, { status: 200, headers: { "Content-Type": "application/json" } }));
  }
  if (method === "GET" && url.includes("/api/google-sheet-tokens")) {
    return Promise.resolve(new Response(FAKE_TOKENS, { status: 200, headers: { "Content-Type": "application/json" } }));
  }
  return realFetch.apply(this, arguments);
};
`;

const SCENARIO_SOURCE = `
// scn: "s1"(auto/total/默认) | "s2_custom"(custom K线) | "s3_random"(随机价) |
//      "s4_nplus1"(n_plus_1 + 近年/全年 + 排除[0.5,2] + 随机价)
window.__capturedPayloads = [];
const fire = (el) => { if (el) el.dispatchEvent(new Event("change", { bubbles: true })); };
const byId = (id) => document.getElementById(id);
const setVal = (id, v) => { const el = byId(id); if (el) el.value = v; return !!el; };
const check = (el, on) => { if (el) { el.checked = on; fire(el); } };
const clickRadio = (name, value) => {
  const el = document.querySelector('input[name="' + name + '"][value="' + value + '"]');
  if (el) { el.checked = true; fire(el); }
};
clickRadio("kline_source", "auto");
clickRadio("count_mode", "total");
clickRadio("token_type", "json");
setVal("token_json", '{"x":1}');
const tokSel = byId("token_id");
if (tokSel) {
  if (!tokSel.querySelector('option[value="__random__"]')) {
    const opt = document.createElement("option");
    opt.value = "__random__";
    tokSel.appendChild(opt);
  }
  tokSel.value = "__random__";
}
const recent = byId("date_range_recent"); if (recent) recent.checked = false;
const full = byId("date_range_full"); if (full) full.checked = false;
document.querySelectorAll(".recent-year-checkbox").forEach((cb) => { cb.checked = false; });
setVal("price_mode", "sp_price"); fire(byId("price_mode"));
setVal("kline_adjustment", "back");
setVal("kline_data_source", "dfcf");
setVal("start_date", "2021-08-20");
setVal("end_date", "2025-08-20");
setVal("param1", '["SCHD"]');
setVal("param2", '["1x","2x"]');
setVal("param3", "[3]");
if (byId("random_price_range")) setVal("random_price_range", "open_close");
if (byId("random_group_count")) setVal("random_group_count", "2");
const list = document.getElementById("sheet-config-list");
if (list && list.querySelectorAll(".sheet-config-item").length === 0) {
  const addBtn = document.getElementById("add-sheet-config-btn");
  if (addBtn) addBtn.click();
}
const item = list && list.querySelector(".sheet-config-item");
if (item) {
  const sel = item.querySelector(".google-sheet-select");
  if (sel) {
    if (!sel.querySelector('option[value="smoke-sheet-1"]')) {
      const opt = document.createElement("option");
      opt.value = "smoke-sheet-1";
      sel.appendChild(opt);
    }
    sel.value = "smoke-sheet-1";
  }
}
if (scn === "s2_custom") clickRadio("kline_source", "custom");
if (scn === "s3_random") { setVal("price_mode", "random_price"); fire(byId("price_mode")); }
if (scn === "s4_nplus1") {
  clickRadio("count_mode", "n_plus_1");
  check(byId("date_range_recent"), true);
  check(byId("date_range_full"), true);
  check(byId("exclude_year_half"), true);
  check(byId("exclude_year_2"), true);
  setVal("price_mode", "random_price"); fire(byId("price_mode"));
}
const btn = document.getElementById("execute-btn");
if (btn) btn.click();
`;
