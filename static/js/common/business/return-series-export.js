// ------------------------------
// 收益序列导出组件（跨页复用）：后端只提供累计收益序列与产品比例（纯数据），
// 净值 / 当天收益率 / 加权日收益 / 组合累计全部写入 Excel 公式，打开文件
// 自动计算（fullCalcOnLoad），中间过程以公式形式完全透明可审计。
//
// 组合口径与后端 portfolio_combiner 一致，由公式布局保证：
// - 只取各产品共同交易日（交集），按日期升序；
// - 各产品日收益在共同区间内计算，首日基线净值 1.0（首日日收益 = 累计 - 1）；
// - 权重不做归一化，直接按比例小数加权后复利还原累计。
//
// 依赖引入顺序：api.js（Api.endpoints）→ 本文件 → 页面 JS；
// SheetJS 按需加载本地 /static/js/xlsx.mini.min.js（mini 构建即可满足公式写入）；
// 页面调用：Biz.returnSeriesExport.exportAndDownload({
//   taskId,      // 任务 ID（必填，可为函数）
//   taskName,    // 文件名用任务名（可选，可为函数，缺省用 taskId）
//   groupKey,    // 参数方案 group_key（可选，可为函数；空则导出返回的全部方案）
//   ratios,      // 页面当前比例（可选，可为函数；空则后端用任务默认比例）
//   onDone,      // 导出成功回调（可选，参数为后端 payload）
// });
// ------------------------------
(function () {
  "use strict";
  window.Biz = window.Biz || {};

  const SHEETJS_LOCAL_URL = "/static/js/xlsx.mini.min.js";
  const DATA_START_ROW = 3; // 产品 sheet：第 1 行标题、第 2 行表头、第 3 行起数据。
  const CUM_INDEX_COL = "B"; // 产品 sheet 累计收益列（组合表跨表引用固定取这两列）。
  const CUM_START_COL = "C";

  let sheetJsPromise = null;

  function resolveOption(value, fallback) {
    const resolved = typeof value === "function" ? value() : value;
    return resolved === undefined || resolved === null ? fallback : resolved;
  }

  // SheetJS 按需加载（单例 Promise），失败时清空缓存允许重试。
  function ensureSheetJs() {
    if (window.XLSX) {
      return Promise.resolve(window.XLSX);
    }
    if (!sheetJsPromise) {
      sheetJsPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = SHEETJS_LOCAL_URL;
        script.onload = () => resolve(window.XLSX);
        script.onerror = () => {
          sheetJsPromise = null;
          reject(new Error("Excel 导出库加载失败（/static/js/xlsx.mini.min.js）"));
        };
        document.head.appendChild(script);
      });
    }
    return sheetJsPromise;
  }

  function columnLetter(index) {
    // 0 → A，26 → AA（组合表列数随产品数增长）。
    let letter = "";
    let value = index;
    while (value >= 0) {
      letter = String.fromCharCode(65 + (value % 26)) + letter;
      value = Math.floor(value / 26) - 1;
    }
    return letter;
  }

  function sanitizeExcelSheetName(name, fallback, used) {
    // Excel sheet 名禁止 \ / : * ? [ ] 且 ≤31 字符，重复时追加序号。
    let base =
      String(name == null ? "" : name)
        .replace(/[\\/:*?[\]]/g, "_")
        .trim() || fallback;
    base = base.slice(0, 28);
    let sheetName = base;
    let suffix = 1;
    while (used.has(sheetName)) {
      const suffixText = `_${suffix++}`;
      sheetName = base.slice(0, 28 - suffixText.length) + suffixText;
    }
    used.add(sheetName);
    return sheetName;
  }

  function buildExcelDownloadName(taskName, taskId) {
    const safeName = String(taskName || taskId)
      .trim()
      .replace(/[\\/:*?"<>|]/g, "_")
      .replace(/[ .]+$/g, "");
    return `${safeName || taskId}_收益序列.xlsx`;
  }

  function quotedSheetRef(sheetName, cell) {
    return `'${sheetName}'!${cell}`;
  }

  function productLabel(meta) {
    return (
      meta.product_name ||
      meta.stock_code ||
      `产品${meta.product_index + 1}`
    );
  }

  // 产品 sheet：累计收益原值 + 公式列（净值、当天收益率）。
  // 当天收益率首日基线 1.0（= 累计 - 1），与组合器 cumulative_to_daily 一致。
  // 返回 { sheetName, dateRowMap } 供组合 sheet 跨表引用。
  // 单品任务（isMulti=false）同一股票会有多条序列，sheet 名带"结果 N"区分。
  function appendProductSheet(workbook, usedNames, entry, isMulti) {
    const name = isMulti
      ? entry.stock_code || entry.stock_name || `产品${entry.product_index + 1}`
      : `${entry.stock_code || entry.stock_name || "结果"}-结果${entry.product_index + 1}`;
    const titleParts = [
      `${entry.stock_name || entry.stock_code || name}（${entry.stock_code || "-"}）`,
    ];
    if (entry.ratio != null) {
      titleParts.push(`比例 ${entry.ratio}`);
    }
    titleParts.push(`${entry.start_date || "-"} ~ ${entry.end_date || "-"}`);
    const header = [
      "日期",
      "指数累计收益",
      "策略累计收益",
      "指数净值",
      "策略净值",
      "指数当天收益率",
      "策略当天收益率",
    ];
    const aoa = [[titleParts.join(" · ")], header];
    const dateRowMap = {};
    (entry.rows || []).forEach((row, index) => {
      const excelRow = DATA_START_ROW + index;
      const prevExcelRow = excelRow - 1;
      dateRowMap[String(row.date)] = excelRow;
      // 注意：公式必须用显式 {f:} 单元格——aoa_to_sheet 不会把 "=..." 字符串转成公式。
      aoa.push([
        row.date,
        row.index_return,
        row.start_return,
        { f: `1+B${excelRow}` },
        { f: `1+C${excelRow}` },
        {
          f:
            index === 0
              ? `B${excelRow}-1`
              : `B${excelRow}/B${prevExcelRow}-1`,
        },
        {
          f:
            index === 0
              ? `C${excelRow}-1`
              : `C${excelRow}/C${prevExcelRow}-1`,
        },
      ]);
    });
    const sheet = XLSX.utils.aoa_to_sheet(aoa);
    sheet["!cols"] = Array.from({ length: header.length }, () => ({ wch: 16 }));
    const sheetName = sanitizeExcelSheetName(
      name,
      `产品${entry.product_index + 1}`,
      usedNames,
    );
    XLSX.utils.book_append_sheet(workbook, sheet, sheetName);
    return { sheetName, dateRowMap };
  }

  // 比例组合 sheet：除日期外全部为公式。
  // - 各产品日收益：跨表引用该产品累计收益列，共同区间内相邻两日相除，
  //   首日基线 1.0（= 累计 - 1），与 cumulative_to_daily 语义一致；
  // - 加权日收益：Σ(产品日收益 × 权重)，权重不做归一化；
  // - 组合累计：加权日收益逐日复利（首日 = 加权日收益）。
  function appendPortfolioSheet(workbook, usedNames, portfolio) {
    const { baseName, products } = portfolio;
    const includedProducts = portfolio.includedProducts;
    const seriesByProduct = portfolio.seriesByProduct;

    // 共同交易日 = 参与组合产品日期集合的交集（升序）。
    let commonDates = null;
    includedProducts.forEach((meta) => {
      const dates = Object.keys(
        seriesByProduct[meta.product_index].dateRowMap,
      );
      commonDates =
        commonDates == null
          ? dates
          : commonDates.filter((date) => dates.includes(date));
    });
    commonDates = (commonDates || []).sort();
    if (!commonDates.length) {
      return false;
    }

    // 列布局：A 日期；每产品 2 列（指数/策略日收益）；加权 2 列；累计 2 列。
    const header = ["日期"];
    includedProducts.forEach((meta) => {
      header.push(
        `${productLabel(meta)}·指数日收益`,
        `${productLabel(meta)}·策略日收益`,
      );
    });
    header.push(
      "组合指数日收益（加权）",
      "组合策略日收益（加权）",
      "组合指数累计收益",
      "组合策略累计收益",
    );
    const weightedIndexCol = columnLetter(1 + includedProducts.length * 2);
    const weightedStartCol = columnLetter(2 + includedProducts.length * 2);
    const cumIndexCol = columnLetter(3 + includedProducts.length * 2);
    const cumStartCol = columnLetter(4 + includedProducts.length * 2);

    // 比例说明区。
    const ratioLines = includedProducts.map((meta) => [
      `${productLabel(meta)}（${meta.stock_code || "-"}）`,
      `${meta.ratio}%（权重 ${meta.weight}）`,
    ]);
    const excluded = products.filter((meta) => !meta.included);
    if (excluded.length) {
      ratioLines.push([
        excluded.map(productLabel).join("、"),
        "0%（不参与组合）",
      ]);
    }
    const aoa = [
      ["比例组合 · 比例说明"],
      ...ratioLines,
      [
        "算法：各产品日收益取自各自 sheet 的累计收益（共同交易日区间内，首日基线 1.0），按权重加权后复利还原为组合累计收益；权重不做归一化。",
      ],
      [],
      header,
    ];
    const headerRow = aoa.length; // 表头所在 Excel 行（1-based）。

    commonDates.forEach((date, index) => {
      const excelRow = headerRow + 1 + index;
      const values = [date];
      includedProducts.forEach((meta, position) => {
        const ref = seriesByProduct[meta.product_index];
        const currentRow = ref.dateRowMap[date];
        const prevRow =
          index > 0 ? ref.dateRowMap[commonDates[index - 1]] : null;
        const dailyIndexCol = columnLetter(1 + position * 2);
        const dailyStartCol = columnLetter(2 + position * 2);
        values.push(
          {
            f:
              prevRow == null
                ? `${quotedSheetRef(ref.sheetName, `${CUM_INDEX_COL}${currentRow}`)}-1`
                : `${quotedSheetRef(ref.sheetName, `${CUM_INDEX_COL}${currentRow}`)}/${quotedSheetRef(ref.sheetName, `${CUM_INDEX_COL}${prevRow}`)}-1`,
          },
          {
            f:
              prevRow == null
                ? `${quotedSheetRef(ref.sheetName, `${CUM_START_COL}${currentRow}`)}-1`
                : `${quotedSheetRef(ref.sheetName, `${CUM_START_COL}${currentRow}`)}/${quotedSheetRef(ref.sheetName, `${CUM_START_COL}${prevRow}`)}-1`,
          },
        );
      });
      const weightedIndexTerms = includedProducts
        .map(
          (meta, position) =>
            `${columnLetter(1 + position * 2)}${excelRow}*${meta.weight}`,
        )
        .join("+");
      const weightedStartTerms = includedProducts
        .map(
          (meta, position) =>
            `${columnLetter(2 + position * 2)}${excelRow}*${meta.weight}`,
        )
        .join("+");
      values.push(
        { f: `=${weightedIndexTerms}` },
        { f: `=${weightedStartTerms}` },
        {
          f:
            index === 0
              ? `${weightedIndexCol}${excelRow}`
              : `${cumIndexCol}${excelRow - 1}*(1+${weightedIndexCol}${excelRow})`,
        },
        {
          f:
            index === 0
              ? `${weightedStartCol}${excelRow}`
              : `${cumStartCol}${excelRow - 1}*(1+${weightedStartCol}${excelRow})`,
        },
      );
      aoa.push(values);
    });

    const sheet = XLSX.utils.aoa_to_sheet(aoa);
    sheet["!cols"] = Array.from({ length: header.length }, () => ({ wch: 16 }));
    XLSX.utils.book_append_sheet(
      workbook,
      sheet,
      sanitizeExcelSheetName(baseName, "比例组合", usedNames),
    );
    return true;
  }

  function buildWorkbook(payload, options) {
    const usedNames = new Set();
    const workbook = XLSX.utils.book_new();
    // mini 构建不写 CalcPr/fullCalcOnLoad；公式不带缓存值，
    // Excel/WPS 打开时会对无缓存结果的公式自动重算。

    const groupKey = options.groupKey != null ? String(options.groupKey) : null;
    let series = payload.series || [];
    if (groupKey != null) {
      series = series.filter((item) => String(item.group_key) === groupKey);
    }
    if (!series.length) {
      throw new Error("没有可导出的收益序列");
    }
    const products = payload.products || [];
    const includedProducts = products.filter(
      (item) => item.included && item.weight != null,
    );
    const isMulti = !!payload.task?.is_multi_product;

    const groupKeys = [];
    series.forEach((entry) => {
      const key = String(entry.group_key);
      if (!groupKeys.includes(key)) {
        groupKeys.push(key);
      }
    });
    const multiGroup = groupKeys.length > 1;

    groupKeys.forEach((key) => {
      const entries = series.filter(
        (entry) => String(entry.group_key) === key,
      );
      const refs = {};
      entries.forEach((entry) => {
        refs[entry.product_index] = appendProductSheet(
          workbook,
          usedNames,
          entry,
          isMulti,
        );
      });
      if (!isMulti || !includedProducts.length) {
        return;
      }
      const seriesByProduct = {};
      const missing = includedProducts.some((meta) => {
        const ref = refs[meta.product_index];
        if (!ref) {
          return true;
        }
        seriesByProduct[meta.product_index] = ref;
        return false;
      });
      if (missing) {
        // 该方案缺少参与组合的产品序列：不生成组合 sheet（与组合器空结果一致）。
        return;
      }
      appendPortfolioSheet(workbook, usedNames, {
        baseName: multiGroup ? `比例组合-方案${Number(key) + 1}` : "比例组合",
        products,
        includedProducts,
        seriesByProduct,
      });
    });

    XLSX.writeFile(
      workbook,
      buildExcelDownloadName(options.taskName, options.taskId),
    );
  }

  // 拉取后端纯数据并生成带公式的 Excel。
  async function exportAndDownload(options) {
    await ensureSheetJs();
    const taskId = resolveOption(options.taskId);
    if (!taskId) {
      throw new Error("缺少任务 ID");
    }
    const groupKey = resolveOption(options.groupKey, null);
    const ratios = resolveOption(options.ratios, null);
    const payload = await Api.endpoints.backtestMulti.returnSeries(
      encodeURIComponent(taskId),
      { ratios, group_key: groupKey },
    );
    buildWorkbook(payload, {
      taskId,
      taskName: resolveOption(options.taskName, taskId),
      groupKey,
    });
    if (typeof options.onDone === "function") {
      options.onDone(payload);
    }
    return payload;
  }

  Biz.returnSeriesExport = { exportAndDownload };
})();
