// admin 基座侧栏脚本（templates/admin/base.html 内联脚本原样抽离，F4）。
// 负责 #templateSidebarMenu 折叠状态记忆/恢复（admin 族各页经 common/admin-shell.js 引入）。
document.addEventListener("DOMContentLoaded", function () {
  const sidebarMenu = document.getElementById("templateSidebarMenu");

  function syncToggleState(element, expanded) {
    if (!element) {
      return;
    }
    const toggle = document.querySelector(`[data-bs-target="#${element.id}"]`);
    if (toggle) {
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    }
  }

  function saveCollapseState() {
    const collapseElements = sidebarMenu
      ? Array.from(sidebarMenu.querySelectorAll(".collapse"))
      : [];
    const collapseState = {};
    collapseElements.forEach((element) => {
      collapseState[element.id] = element.classList.contains("show");
    });
    localStorage.setItem("sidebarCollapseState", JSON.stringify(collapseState));
  }

  function restoreCollapseState() {
    const collapseElements = sidebarMenu
      ? Array.from(sidebarMenu.querySelectorAll(".collapse"))
      : [];
    const savedState = localStorage.getItem("sidebarCollapseState");
    if (savedState) {
      const collapseState = JSON.parse(savedState);
      Object.keys(collapseState).forEach((elementId) => {
        const element = document.getElementById(elementId);
        if (!element) {
          return;
        }
        if (collapseState[elementId]) {
          element.classList.add("show");
          syncToggleState(element, true);
        } else {
          element.classList.remove("show");
          syncToggleState(element, false);
        }
      });
      return;
    }

    collapseElements.forEach((element) => {
      const hasActiveLink = element.querySelector(".nav-link.active");
      const shouldShow = Boolean(hasActiveLink);
      element.classList.toggle("show", shouldShow);
      syncToggleState(element, shouldShow);
    });
  }

  const observer = new MutationObserver(function () {
    const collapseElements = sidebarMenu
      ? Array.from(sidebarMenu.querySelectorAll(".collapse"))
      : [];
    collapseElements.forEach((element) => {
      if (element.dataset.boundCollapseEvents === "true") {
        return;
      }
      element.dataset.boundCollapseEvents = "true";
      element.addEventListener("shown.bs.collapse", saveCollapseState);
      element.addEventListener("hidden.bs.collapse", saveCollapseState);
      syncToggleState(element, element.classList.contains("show"));
    });
    restoreCollapseState();
  });

  if (sidebarMenu) {
    observer.observe(sidebarMenu, { childList: true, subtree: true });
  }
});
