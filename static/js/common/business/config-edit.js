// ------------------------------
// c4/c5/c7/c1_1 详情页共享：配置展示 helpers（02 §3.6，F3 收敛 pass）。
// 历史上本文件还承载「编辑配置弹窗」的回填/收集逻辑；编辑已统一迁移到
// 创建页 edit 模式（/google-sheet/create?version=<v>&edit_task_id=...，
// 回填与提交由 Biz.ctaskCreate 处理），弹窗相关函数已随迁移删除。
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

  function isRandomPriceMode(config) {
    if (String((config && config.price_mode) || "") === "random_price") {
      return true;
    }
    // C1.1 运行期强制随机价，旧任务缺 price_mode 时也按随机价展示
    return isC1_1Config(config);
  }

  // C1.1 真实价取值（random_price 模式子标记）：AG 直写真实字段，无随机语义
  const REAL_PRICE_RANGES = ["kp_price", "sp_price", "high_price", "low_price"];

  function isRealPriceRange(config) {
    return REAL_PRICE_RANGES.includes(
      String((config && config.random_price_range) || "").trim()
    );
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
      high_low: "最高价 - 最低价（随机）",
      open_close: "开盘价 - 收盘价（随机）",
      kp_price: "开盘价（真实）",
      sp_price: "收盘价（真实）",
      high_price: "最高价（真实）",
      low_price: "最低价（真实）",
    });
  }

  function formatRandomSeriesMode(value) {
    return formatConfigDisplayValue(value || "per_window", {
      per_window: "各窗口独立随机",
      full_truncate: "全区间生成后按窗口截断",
    });
  }

  // 详情页可见的“随机价配置”卡片（random_price / C1.1 才渲染）；
  // 真实价取值无随机语义：标题改「取价配置」，且不展示随机组数/序列模式
  function appendRandomPriceConfigBlock(config, container) {
    if (!container || !isRandomPriceMode(config)) {
      return;
    }

    const isRealRange = isRealPriceRange(config);
    const block = document.createElement("div");
    block.className = "mb-3";
    block.innerHTML = isRealRange
      ? '<strong class="d-block mb-2">取价配置</strong>'
      : '<strong class="d-block mb-2">随机价配置</strong>';

    const grid = document.createElement("div");
    grid.className = "detail-config-grid";
    const items = [
      {
        label: isRealRange ? "AG 取价范围" : "随机价格范围",
        value: formatRandomPriceRange(config.random_price_range),
        icon: "bi-shuffle",
      },
    ];
    if (!isRealRange) {
      const randomGroupCount = Math.max(
        1,
        parseInt(config.random_group_count, 10) || 1
      );
      items.push(
        {
          label: "随机组数",
          value: String(randomGroupCount),
          icon: "bi-collection",
        },
        {
          label: "随机序列模式",
          value: formatRandomSeriesMode(config.random_series_mode),
          icon: "bi-diagram-3",
        }
      );
    }
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

  Biz.configEdit = {
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
    isRandomPriceMode: isRandomPriceMode,
    isRealPriceRange: isRealPriceRange,
  };
})();
