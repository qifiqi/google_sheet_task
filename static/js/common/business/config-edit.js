// ------------------------------
// c4/c5/c7 详情页三胞胎共享：编辑配置弹窗（02 §3.6，F3 收敛 pass）。
// 来源：static/js/pages/google_sheet_c{4,5,7}_detail.js（三版规范化后逐字相同，正本取自 c4）。
// 页面差异逻辑仍留在 pages 层；页面调用点经 Biz.configEdit.* 访问。
// ------------------------------
(function () {
  window.Biz = window.Biz || {};

  // 任务 config 值属用户可控输入，插入 innerHTML/属性前必须转义（存储型 XSS 防线）。
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // 打开弹窗时暂存的 parameters[1..]（保存时原样回写）
  var originalExtraParameters = [];

  // 最近一次打开弹窗时的 config，用于价格类型与版本联动
  var editModalConfig = {};

  function hasSheetModelVersion(config, version) {
    return (
      Array.isArray(config && config.sheets) &&
      config.sheets.some(function (sheet) {
        return sheet && sheet.model_version === version;
      })
    );
  }

  function isC1_1Config(config) {
    return hasSheetModelVersion(config, "c1_1");
  }

  function isC7V03Config(config) {
    return hasSheetModelVersion(config, "c7_0_3");
  }

  function isRandomPriceMode(config) {
    if (String((config && config.price_mode) || "") === "random_price") {
      return true;
    }
    // C1.1 运行期强制随机价，旧任务缺 price_mode 时也按随机价展示
    return isC1_1Config(config);
  }

  function openEditConfigModal() {
    if (!currentTaskData) {
      showNotification("任务数据未加载", "error");
      return;
    }

    // 解析任务配置（必须是包含 sheets / parameters 结构的对象）
    var config = currentTaskData.config || {};
    if (typeof config === "string") {
      try {
        config = JSON.parse(config);
      } catch (e) {
        console.warn("解析任务配置失败，将按原始字符串展示", e);
      }
    }

    // 任务基本信息
    const editTaskNameEl = document.getElementById("edit-task-name");
    if (editTaskNameEl) {
      editTaskNameEl.value = currentTaskData.name || "";
    }
    const editTaskDescEl = document.getElementById("edit-task-description");
    if (editTaskDescEl) {
      editTaskDescEl.value = currentTaskData.description || "";
    }

    // 主参数：parameters[0] 渲染为 chips
    var mainParams = Array.isArray(config.parameters && config.parameters[0])
      ? config.parameters[0].slice()
      : [];
    renderEditProductCodeChips(mainParams);

    // parameters[1..] 本弹窗不提供编辑，打开时暂存，保存时经 takeEditExtraParameters 原样回写
    //（防止 payload 整体覆盖导致参数组缩水）
    originalExtraParameters = Array.isArray(config.parameters)
      ? config.parameters.slice(1)
      : [];

    // 完整 parameters 只读展示
    const paramsRawEl = document.getElementById("edit-parameters-raw");
    if (paramsRawEl) {
      try {
        paramsRawEl.value = config.parameters
          ? JSON.stringify(config.parameters, null, 2)
          : "";
      } catch (e) {
        paramsRawEl.value = "";
      }
    }

    // sheets 多行输入
    const sheets = Array.isArray(config.sheets) ? config.sheets : [];
    renderEditSheetsRows(sheets);

    // 更多参数区域（缺省对齐 C 系创建页/详情页口径 total）
    const countModeEl = document.getElementById("edit-count-mode");
    if (countModeEl) {
      countModeEl.value = config.count_mode || "total";
    }

    const fullModeEl = document.getElementById("edit-date-range-full");
    const recentModeEl = document.getElementById("edit-date-range-recent");
    let drmList = [];
    if (Array.isArray(config.date_range_mode)) {
      drmList = config.date_range_mode;
    } else if (
      typeof config.date_range_mode === "string" &&
      config.date_range_mode
    ) {
      drmList = [config.date_range_mode];
    }
    if (drmList.length === 0) {
      drmList = ["full"];
    }

    function applyEditDateRangeModes(enableOnly) {
      const currentMode = (countModeEl && countModeEl.value) || "n_plus_1";
      const enable = currentMode === "n_plus_1";
      if (fullModeEl) {
        fullModeEl.disabled = !enable;
        if (!enable) {
          fullModeEl.checked = false;
        } else if (!enableOnly) {
          fullModeEl.checked = drmList.includes("full");
        }
      }
      if (recentModeEl) {
        recentModeEl.disabled = !enable;
        if (!enable) {
          recentModeEl.checked = false;
        } else if (!enableOnly) {
          recentModeEl.checked = drmList.includes("recent");
        }
      }
    }

    applyEditDateRangeModes(false);
    if (countModeEl) {
      countModeEl.addEventListener("change", function () {
        applyEditDateRangeModes(true);
        // 等所有联动监听执行完再决定“移除的近年区间”是否可见
        setTimeout(syncEditExcludeYearsVisibility, 0);
      });
    }

    const startDateEl = document.getElementById("edit-start-date");
    if (startDateEl) {
      startDateEl.value = config.start_date || "";
    }

    const endDateEl = document.getElementById("edit-end-date");
    if (endDateEl) {
      endDateEl.value = config.end_date || "";
    }

    const marketTypeEl = document.getElementById("edit-market-type");
    if (marketTypeEl) {
      marketTypeEl.value = config.market_type || "";
    }

    const editProxyUrlEl = document.getElementById("edit-proxy-url");
    if (editProxyUrlEl) {
      editProxyUrlEl.value = config.proxy_url || "";
    }

    populateEditKlinePriceFields(config);

    // 打开模态框
    if (editConfigModal) {
      editConfigModal.show();
    }
  }

  function renderEditProductCodeChips(codes) {
    const container = document.getElementById("edit-product-code-chips");
    if (!container) return;
    container.innerHTML = "";

    const unique = [];
    const seen = new Set();
    (codes || []).forEach((c) => {
      const val = String(c).trim();
      if (!val || seen.has(val)) return;
      seen.add(val);
      unique.push(val);
    });

    unique.forEach((code) => {
      const chip = document.createElement("span");
      chip.className = "badge bg-primary d-flex align-items-center me-1 mb-1";
      chip.style.cursor = "default";
      chip.dataset.value = code;
      chip.innerHTML = `
                <span class="me-1">${escapeHtml(code)}</span>
                <button type="button" class="btn btn-sm btn-light btn-close p-0 ms-1" aria-label="删除" style="font-size: 0.5rem;"></button>
            `;
      const closeBtn = chip.querySelector("button");
      if (closeBtn) {
        closeBtn.addEventListener("click", function (e) {
          e.stopPropagation();
          chip.remove();
        });
      }
      container.appendChild(chip);
    });
  }

  function renderEditSheetsRows(sheets) {
    const list = document.getElementById("edit-sheets-list");
    if (!list) return;
    list.innerHTML = "";
    const data = Array.isArray(sheets) && sheets.length > 0 ? sheets : [{}];

    data.forEach((s) => {
      const row = document.createElement("div");
      row.className = "row g-2 align-items-end mb-2 edit-sheet-row";
      row.innerHTML = `
                <div class="col-md-4">
                    <label class="form-label small mb-1">spreadsheet_id</label>
                    <input type="text" class="form-control form-control-sm edit-sheet-spreadsheet-id" value="${escapeHtml(s.spreadsheet_id || "")}">
                </div>
                <div class="col-md-4">
                    <label class="form-label small mb-1">title</label>
                    <input type="text" class="form-control form-control-sm edit-sheet-title" value="${escapeHtml(s.title || "")}">
                </div>
                <div class="col-md-4">
                    <label class="form-label small mb-1">sheet_name</label>
                    <input type="text" class="form-control form-control-sm edit-sheet-name" value="${escapeHtml(s.sheet_name || "")}">
                </div>
            `;
      // 逐表附加键（model_version/google_sheet_id 等）不在弹窗编辑，
      // 随行暂存，collectEditSheetsRows 时回写，避免保存后丢失
      const extra = {};
      Object.keys(s || {}).forEach((key) => {
        if (!["spreadsheet_id", "title", "sheet_name"].includes(key)) {
          extra[key] = s[key];
        }
      });
      if (Object.keys(extra).length) {
        row.dataset.extraKeys = JSON.stringify(extra);
      }
      if (s && s.model_version) {
        const badge = document.createElement("span");
        badge.className = "badge bg-info text-dark ms-1 mb-2";
        badge.textContent = formatModelVersion(s.model_version);
        row.appendChild(badge);
      }
      list.appendChild(row);
    });
  }

  // 收集弹窗内 sheets 多行：三个可编辑字段覆盖行内值，逐表附加键原样带回
  function collectEditSheetsRows() {
    const list = document.getElementById("edit-sheets-list");
    const sheets = [];
    if (!list) return sheets;
    list.querySelectorAll(".edit-sheet-row").forEach((row) => {
      const sidEl = row.querySelector(".edit-sheet-spreadsheet-id");
      const titleEl = row.querySelector(".edit-sheet-title");
      const nameEl = row.querySelector(".edit-sheet-name");
      const sid = sidEl ? sidEl.value.trim() : "";
      const sname = nameEl ? nameEl.value.trim() : "";
      const title = titleEl ? titleEl.value.trim() : "";
      if (sid || sname || title) {
        let extra = {};
        if (row.dataset.extraKeys) {
          try {
            extra = JSON.parse(row.dataset.extraKeys) || {};
          } catch (e) {
            extra = {};
          }
        }
        const item = Object.assign({}, extra, {
          spreadsheet_id: sid || null,
          sheet_name: sname || null,
        });
        if (title) {
          item.title = title;
        }
        sheets.push(item);
      }
    });
    return sheets;
  }

  // 取回打开弹窗时暂存的 parameters[1..]（每次打开弹窗重新暂存）
  function takeEditExtraParameters() {
    return originalExtraParameters.slice();
  }

  function collectEditProductCodesFromChips() {
    const container = document.getElementById("edit-product-code-chips");
    if (!container) return [];
    const vals = [];
    const seen = new Set();
    container.querySelectorAll("[data-value]").forEach((el) => {
      const v = (el.dataset.value || "").trim();
      if (v && !seen.has(v)) {
        seen.add(v);
        vals.push(v);
      }
    });
    return vals;
  }

  function createConfigGridItem(item) {
    const col = document.createElement("div");
    col.className = "detail-config-item d-flex align-items-start";
    col.innerHTML = `
            <i class="${item.icon} text-muted me-3 mt-1"></i>
            <div class="flex-grow-1 min-w-0">
                <div class="detail-config-label">${item.label}</div>
                <div class="detail-config-value">${escapeHtml(item.value)}</div>
            </div>
        `;
    return col;
  }

  function formatConfigDisplayValue(value, mapping) {
    if (Array.isArray(value)) {
      const formatted = value
        .map((item) => formatConfigDisplayValue(item, mapping))
        .filter(Boolean);
      return formatted.length ? formatted.join("、") : "-";
    }

    if (value === null || value === undefined || value === "") {
      return "-";
    }

    const normalized = String(value);
    return mapping && mapping[normalized] ? mapping[normalized] : normalized;
  }

  function formatCountMode(value) {
    return formatConfigDisplayValue(value, {
      total: "总数",
      n_plus_1: "N+1",
    });
  }

  function formatDateRangeMode(value) {
    return formatConfigDisplayValue(value, {
      full: "整年",
      recent: "近年",
    });
  }

  function formatMarketType(value) {
    return formatConfigDisplayValue(value, {
      cn: "A股",
      us: "美股",
    });
  }

  function formatTokenType(value) {
    return formatConfigDisplayValue(value, {
      file: "Token 文件",
      json: "Token JSON",
    });
  }

  // K线数据源标签（与创建页数据源下拉口径一致，database 为内置K线库）
  function formatKlineDataSource(value) {
    return formatConfigDisplayValue(value, {
      akshare: "AKShare",
      dfcf: "东方财富",
      qq: "腾讯",
      yahoo: "Yahoo",
      tdx: "通达信",
      database: "内置K线库",
    });
  }

  function formatPriceMode(value) {
    return formatConfigDisplayValue(value, {
      kp_price: "开盘价",
      sp_price: "收盘价",
      vwap_price: "加权平均价",
      random_price: "随机价",
      ohlc_price: "OHLC（开高低收）",
    });
  }

  function formatKlineSource(value) {
    return formatConfigDisplayValue(value || "auto", {
      auto: "自动K线",
      custom: "自定义K线",
    });
  }

  function formatKlineAdjustment(value) {
    return formatConfigDisplayValue(value || "forward", {
      forward: "前复权",
      back: "后复权",
      none: "不复权",
    });
  }

  function formatRandomPriceRange(value) {
    return formatConfigDisplayValue(value || "high_low", {
      high_low: "最高价 - 最低价",
      open_close: "开盘价 - 收盘价",
    });
  }

  function formatRandomSeriesMode(value) {
    return formatConfigDisplayValue(value || "per_window", {
      per_window: "各窗口独立随机",
      full_truncate: "全区间生成后按窗口截断",
    });
  }

  // 详情页可见的“随机价配置”卡片（random_price / C1.1 才渲染）
  function appendRandomPriceConfigBlock(config, container) {
    if (!container || !isRandomPriceMode(config)) {
      return;
    }

    const block = document.createElement("div");
    block.className = "mb-3";
    block.innerHTML = '<strong class="d-block mb-2">随机价配置</strong>';

    const grid = document.createElement("div");
    grid.className = "detail-config-grid";
    const randomGroupCount = Math.max(
      1,
      parseInt(config.random_group_count, 10) || 1
    );
    const items = [
      {
        label: "随机价格范围",
        value: formatRandomPriceRange(config.random_price_range),
        icon: "bi-shuffle",
      },
      {
        label: "随机组数",
        value: String(randomGroupCount),
        icon: "bi-collection",
      },
      {
        label: "随机序列模式",
        value: formatRandomSeriesMode(config.random_series_mode),
        icon: "bi-diagram-3",
      },
    ];
    if (
      Object.prototype.hasOwnProperty.call(config, "c1_1_vwap_enabled")
    ) {
      items.push({
        label: "VWAP 计算",
        value: config.c1_1_vwap_enabled === false ? "不计算" : "计算并写入",
        icon: "bi-calculator",
      });
    }
    items.forEach(function (item) {
      grid.appendChild(createConfigGridItem(item));
    });

    block.appendChild(grid);
    container.appendChild(block);
  }

  function renderEditExcludeYearOptions(selected) {
    const container = document.getElementById("edit-exclude-years-options");
    if (!container) return;

    const selectedSet = new Set(
      (Array.isArray(selected) ? selected : []).map(Number)
    );
    container.innerHTML = "";
    [0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].forEach(function (value) {
      const id = "edit-exclude-year-" + String(value).replace(".", "_");
      const wrapper = document.createElement("div");
      wrapper.className = "form-check form-check-inline";
      wrapper.innerHTML = `
                <input class="form-check-input edit-exclude-year" type="checkbox" id="${id}" value="${value}">
                <label class="form-check-label" for="${id}">${value === 0.5 ? "近半年" : "近" + value + "年"}</label>
            `;
      wrapper.querySelector("input").checked = selectedSet.has(value);
      container.appendChild(wrapper);
    });
  }

  function syncEditExcludeYearsVisibility() {
    const container = document.getElementById("edit-exclude-years-container");
    if (!container) return;

    const countModeEl = document.getElementById("edit-count-mode");
    const recentModeEl = document.getElementById("edit-date-range-recent");
    const sourceEl = document.getElementById("edit-kline-source");
    const visible =
      (!countModeEl || countModeEl.value === "n_plus_1") &&
      (!recentModeEl || recentModeEl.checked) &&
      (!sourceEl || sourceEl.value !== "custom");
    container.classList.toggle("d-none", !visible);
  }

  function ensureEmptyOption(select, label) {
    if (!select || select.querySelector('option[value=""]')) {
      return;
    }
    const option = document.createElement("option");
    option.value = "";
    option.textContent = label;
    select.insertBefore(option, select.firstChild);
  }

  function syncEditKlinePriceState() {
    const sourceEl = document.getElementById("edit-kline-source");
    const priceModeEl = document.getElementById("edit-price-mode");
    const adjustmentEl = document.getElementById("edit-kline-adjustment");
    const isCustom = !!sourceEl && sourceEl.value === "custom";
    const c1_1 = isC1_1Config(editModalConfig);
    const forceOhlc =
      isC7V03Config(editModalConfig) &&
      (!sourceEl || sourceEl.value === "auto");

    if (priceModeEl) {
      if (isCustom) {
        priceModeEl.disabled = true;
      } else if (c1_1) {
        priceModeEl.value = "random_price";
        priceModeEl.disabled = true;
      } else if (forceOhlc) {
        priceModeEl.value = "ohlc_price";
        priceModeEl.disabled = true;
      } else {
        priceModeEl.disabled = false;
      }
    }
    if (adjustmentEl) {
      adjustmentEl.disabled = isCustom;
    }

    const randomFields = document.getElementById("edit-random-price-fields");
    if (randomFields) {
      randomFields.classList.toggle(
        "d-none",
        isCustom || !priceModeEl || priceModeEl.value !== "random_price"
      );
    }
    syncEditExcludeYearsVisibility();
  }

  function populateEditKlinePriceFields(config) {
    editModalConfig = config || {};

    const sourceEl = document.getElementById("edit-kline-source");
    const isCustom = !!sourceEl && (config.kline_source || "auto") === "custom";
    if (sourceEl) {
      sourceEl.value = config.kline_source || "auto";
      // K线来源决定 Sheet 输入列布局，创建后不允许在详情页切换
      sourceEl.disabled = true;
      sourceEl.title = "K线来源在任务创建后不可修改，如需切换请创建新任务";
    }

    const priceModeEl = document.getElementById("edit-price-mode");
    if (priceModeEl) {
      if (isCustom) {
        ensureEmptyOption(priceModeEl, "自定义K线（不适用）");
        priceModeEl.value = "";
      } else {
        priceModeEl.value =
          config.price_mode ||
          (isC1_1Config(config) ? "random_price" : "vwap_price");
      }
      if (!priceModeEl._bindedForKlinePrice) {
        priceModeEl.addEventListener("change", syncEditKlinePriceState);
        priceModeEl._bindedForKlinePrice = true;
      }
    }

    const adjustmentEl = document.getElementById("edit-kline-adjustment");
    if (adjustmentEl) {
      if (isCustom) {
        ensureEmptyOption(adjustmentEl, "自定义K线（不适用）");
        adjustmentEl.value = "";
      } else {
        adjustmentEl.value = config.kline_adjustment || "forward";
      }
    }

    const dataSourceEl = document.getElementById("edit-kline-data-source");
    if (dataSourceEl) {
      dataSourceEl.value = config.kline_data_source || "akshare";
    }

    const vwapEl = document.getElementById("edit-c1-1-vwap-enabled");
    if (vwapEl) {
      vwapEl.checked = config.c1_1_vwap_enabled !== false;
    }

    const randomRangeEl = document.getElementById(
      "edit-random-price-range"
    );
    if (randomRangeEl) {
      randomRangeEl.value = config.random_price_range || "high_low";
    }

    const randomGroupEl = document.getElementById(
      "edit-random-group-count"
    );
    if (randomGroupEl) {
      randomGroupEl.value = config.random_group_count || 1;
    }

    const randomSeriesEl = document.getElementById(
      "edit-random-series-mode"
    );
    if (randomSeriesEl) {
      randomSeriesEl.value = config.random_series_mode || "per_window";
    }

    const recentModeEl = document.getElementById("edit-date-range-recent");
    if (recentModeEl && !recentModeEl._bindedForExcludeYears) {
      recentModeEl.addEventListener(
        "change",
        syncEditExcludeYearsVisibility
      );
      recentModeEl._bindedForExcludeYears = true;
    }

    renderEditExcludeYearOptions(config.exclude_recent_years);
    syncEditKlinePriceState();
  }

  function isEditCustomKline() {
    const sourceEl = document.getElementById("edit-kline-source");
    return !!sourceEl && sourceEl.value === "custom";
  }

  // 收集编辑弹窗中的 K线/价格字段；无该区域（C4）时返回空对象
  function collectEditKlinePriceFields() {
    const sourceEl = document.getElementById("edit-kline-source");
    if (!sourceEl) {
      return {};
    }

    const result = {
      kline_source: sourceEl.value || "auto",
    };

    const dataSourceEl = document.getElementById("edit-kline-data-source");
    if (dataSourceEl) {
      result.kline_data_source = dataSourceEl.value || "akshare";
    }

    const vwapEl = document.getElementById("edit-c1-1-vwap-enabled");

    // 自定义K线：价格类型/复权/随机价/近年区间必须为空（后端强校验）
    if (result.kline_source === "custom") {
      result.price_mode = null;
      result.kline_adjustment = null;
      result.random_price_range = null;
      result.random_group_count = null;
      result.random_series_mode = null;
      result.exclude_recent_years = [];
      if (vwapEl) {
        result.c1_1_vwap_enabled = !!vwapEl.checked;
      }
      return result;
    }

    const priceModeEl = document.getElementById("edit-price-mode");
    result.price_mode = priceModeEl
      ? priceModeEl.value || "vwap_price"
      : "vwap_price";

    const adjustmentEl = document.getElementById("edit-kline-adjustment");
    if (adjustmentEl) {
      result.kline_adjustment = adjustmentEl.value || "forward";
    }

    if (result.price_mode === "random_price") {
      const groupEl = document.getElementById("edit-random-group-count");
      const groupCount = groupEl ? parseInt(groupEl.value, 10) : 1;
      if (!Number.isInteger(groupCount) || groupCount < 1) {
        showNotification("随机组数必须是正整数", "error");
        return null;
      }
      const rangeEl = document.getElementById("edit-random-price-range");
      const seriesEl = document.getElementById("edit-random-series-mode");
      result.random_price_range = rangeEl ? rangeEl.value : "high_low";
      result.random_group_count = groupCount;
      result.random_series_mode = seriesEl
        ? seriesEl.value || "per_window"
        : "per_window";
    } else {
      // 非随机价时显式清空，服务端 exclude_none 会移除这些键
      result.random_price_range = null;
      result.random_group_count = null;
      result.random_series_mode = null;
    }

    if (vwapEl) {
      result.c1_1_vwap_enabled = !!vwapEl.checked;
    }

    const excludeContainer = document.getElementById(
      "edit-exclude-years-container"
    );
    result.exclude_recent_years =
      excludeContainer && !excludeContainer.classList.contains("d-none")
        ? Array.prototype.slice
            .call(excludeContainer.querySelectorAll(".edit-exclude-year"))
            .filter(function (el) {
              return el.checked;
            })
            .map(function (el) {
              return Number(el.value);
            })
        : [];

    return result;
  }

  Biz.configEdit = {
    openEditConfigModal: openEditConfigModal,
    renderEditProductCodeChips: renderEditProductCodeChips,
    renderEditSheetsRows: renderEditSheetsRows,
    collectEditSheetsRows: collectEditSheetsRows,
    takeEditExtraParameters: takeEditExtraParameters,
    collectEditProductCodesFromChips: collectEditProductCodesFromChips,
    createConfigGridItem: createConfigGridItem,
    formatConfigDisplayValue: formatConfigDisplayValue,
    formatCountMode: formatCountMode,
    formatDateRangeMode: formatDateRangeMode,
    formatMarketType: formatMarketType,
    formatTokenType: formatTokenType,
    formatKlineDataSource: formatKlineDataSource,
    formatPriceMode: formatPriceMode,
    formatKlineSource: formatKlineSource,
    formatKlineAdjustment: formatKlineAdjustment,
    formatRandomPriceRange: formatRandomPriceRange,
    formatRandomSeriesMode: formatRandomSeriesMode,
    appendRandomPriceConfigBlock: appendRandomPriceConfigBlock,
    collectEditKlinePriceFields: collectEditKlinePriceFields,
    isEditCustomKline: isEditCustomKline,
    isRandomPriceMode: isRandomPriceMode,
  };
})();
