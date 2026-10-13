// ------------------------------
// 返回链接来源页回跳（跨页复用）：
// "返回"按钮在 HTML 里写的 href 是兜底目标；页面若由站内其它页面进入
// （同源 referrer 且不是本页自跳转），则把返回链接改写为来源页，
// 保证"从哪进来就回哪去"；新标签页直开 / 无 referrer / 跨源时维持兜底
// href，仍然落到真实页面。
//
// 用法：返回 <a> 加 data-back-origin 属性，页面引入本文件即可
// （DOMContentLoaded 时自动应用一次；也可手动 Biz.backLink.apply()）。
//
// 依赖引入顺序：无依赖，本文件自足（普通 script，禁 defer/module）。
// ------------------------------
(function () {
  "use strict";
  window.Biz = window.Biz || {};

  // 解析应回跳的来源页地址；不满足条件返回 null（保持兜底 href）。
  function originBackHref() {
    let referrer = null;
    try {
      referrer = document.referrer ? new URL(document.referrer) : null;
    } catch (e) {
      referrer = null;
    }
    if (!referrer || referrer.origin !== window.location.origin) {
      return null;
    }
    // 本页自跳转（刷新或仅 query 变化，如换 task_id 重进）：返回自己没有意义。
    if (referrer.origin + referrer.pathname === window.location.origin + window.location.pathname) {
      return null;
    }
    return referrer.href;
  }

  function apply(root) {
    const scope = root || document;
    scope.querySelectorAll("a[data-back-origin]").forEach(function (link) {
      const resolved = originBackHref();
      if (resolved) {
        link.href = resolved;
      }
    });
  }

  window.Biz.backLink = { apply: apply, originBackHref: originBackHref };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      apply();
    });
  } else {
    apply();
  }
})();
