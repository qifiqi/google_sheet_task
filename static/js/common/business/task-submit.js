// ------------------------------
// c4/c5/c7 创建页三胞胎共享：参数组合展开/保存模板/任务事件（02 §3.6，F3 收敛 pass）。
// 来源：static/js/pages/google_sheet_c{4,5,7}_create.js（三版规范化后逐字相同，正本取自 c4）。
// 页面差异逻辑仍留在 pages 层；页面调用点经 Biz.taskSubmit.* 访问。
// ------------------------------
(function () {
  window.Biz = window.Biz || {};

  function generateCombinations(parameters) {
    const combinations = [];
    const param1 = parameters[0] || [];
    for (const p1 of param1) {
      combinations.push([p1]);
    }
    return combinations;
  }

  function saveAsTemplate() {
    // 获取当前配置
    const config = getCurrentConfig();
    if (!config) {
      return;
    }

    // 预填充模板名称（如果有任务名称）
    const taskName = document.getElementById("task_name").value.trim();
    if (taskName) {
      document.getElementById("templateName").value = taskName + " 模板";
    }

    // 显示保存模板对话框
    const modal = new bootstrap.Modal(
      document.getElementById("saveTemplateModal"),
    );
    modal.show();
  }

  function submitTemplate() {
    const config = getCurrentConfig();
    if (!config) {
      return;
    }

    const name = document.getElementById("templateName").value.trim();
    const description = document
      .getElementById("templateDescription")
      .value.trim();

    if (!name) {
      Biz.formState.showError("请输入模板名称");
      return;
    }

    const templateData = {
      name: name,
      description: description,
      config: config,
    };

    Api.endpoints.template
      .create(templateData)
      .then((data) => {
        const modal = document.getElementById("saveTemplateModal");
        const modalInstance = bootstrap.Modal.getInstance(modal);
        if (modalInstance) {
          modalInstance.hide();
        }
        showNotification("模板保存成功", "success");

        // 重新加载模板列表
        loadTemplates();
      })
      .catch((error) => {
        console.error("保存模板失败:", error);
        Biz.formState.showError((error && error.message) || "保存模板失败");
      });
  }

  Biz.taskSubmit = {
    generateCombinations: generateCombinations,
    saveAsTemplate: saveAsTemplate,
    submitTemplate: submitTemplate,
  };
})();
