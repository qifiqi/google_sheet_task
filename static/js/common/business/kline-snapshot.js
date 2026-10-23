// ------------------------------
// C1.1/C5/C7 详情页共享：随机K线快照 CSV 下载。
// 接口经 common/api.js 的 export 组原始 Response 出口，鉴权由 template-auth.js 拦截。
// ------------------------------
(function () {
  window.Biz = window.Biz || {};

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

  async function run(request, fallback) {
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

  Biz.klineSnapshot = {
    downloadTask: function (taskId) {
      return run(
        function () {
          return Api.endpoints.export.taskKlineSnapshots(taskId);
        },
        `task-${taskId}-kline-snapshots.csv`,
      );
    },
    downloadResult: function (resultId) {
      return run(
        function () {
          return Api.endpoints.export.resultKlineSnapshot(resultId);
        },
        `result-${resultId}-kline-snapshot.csv`,
      );
    },
  };
})();
