const TASK_ID =
  (window.location.pathname.match(/\/global-preview\/([^/]+)/) || [])[1] || "";
// 静态化（03 §3 #1）：原服务端注入的 backToDetailLink/summaryTaskId task_id 改为运行时填充
(function () {
  const backToDetailLinkEl = document.getElementById("backToDetailLink");
  if (backToDetailLinkEl) {
    backToDetailLinkEl.href =
      "/backtest-multi-product/detail/" + encodeURIComponent(TASK_ID);
  }
  const summaryTaskIdEl = document.getElementById("summaryTaskId");
  if (summaryTaskIdEl) {
    summaryTaskIdEl.textContent = TASK_ID;
  }
})();
let previewPayload = null;
let activeGroupKey = null;
let hasUnsavedRatioPreview = false;
let ratioInputsDirty = false;
let appliedRatioSignature = "";

function buildExcelDownloadName() {
  const taskName = String(previewPayload?.task?.name || TASK_ID).trim();
  const safeName = taskName
    .replace(/[\\/:*?"<>|]/g, "_")
    .replace(/[ .]+$/g, "");
  return `${safeName || TASK_ID}.xlsx`;
}

function renderSummary() {
  const task = previewPayload.task || {};
  const summary = previewPayload.summary || {};
  document.getElementById("taskTitleText").textContent =
    `全局预览 · ${task.name || TASK_ID} · ${task.start_date || "-"} ~ ${task.end_date || "-"}`;
  document.getElementById("summaryTaskId").textContent = task.id || TASK_ID;
  document.getElementById("summaryProducts").textContent =
    summary.product_count ?? 0;
  document.getElementById("summaryGroups").textContent =
    summary.group_count ?? 0;
  document.getElementById("summarySuccess").textContent =
    summary.success_results ?? 0;
}

function renderGroupOptions() {
  const select = document.getElementById("groupSelect");
  const groups = Array.isArray(previewPayload.groups)
    ? previewPayload.groups
    : [];
  if (!groups.length) {
    select.innerHTML = '<option value="">暂无参数方案</option>';
    select.disabled = true;
    return;
  }
  select.disabled = false;
  select.innerHTML = groups
    .map(
      (group) => `
        <option value="${escapeHtml(group.group_key)}" ${group.group_key === activeGroupKey ? "selected" : ""}>
            ${escapeHtml(group.group_label)} (${escapeHtml(group.result_count || 0)} 个产品结果)
        </option>
    `,
    )
    .join("");
}

function ratioTotal() {
  return Array.from(document.querySelectorAll(".ratio-input")).reduce(
    (sum, input) => {
      const value = Number(input.value || 0);
      return sum + (Number.isFinite(value) ? value : 0);
    },
    0,
  );
}

function updateRatioStatus() {
  const total = ratioTotal();
  const badge = document.getElementById("ratioTotalBadge");
  const suffix = ratioInputsDirty
    ? "（需计算预览）"
    : hasUnsavedRatioPreview
      ? "（未保存）"
      : "";
  badge.textContent = `合计 ${Number(total.toFixed(4))}%${suffix}`;
  badge.className = "ratio-total-badge is-valid";
}

function renderRatios() {
  const products = Array.isArray(previewPayload.products)
    ? previewPayload.products
    : [];
  document.getElementById("ratioListBody").innerHTML = products
    .map(
      (product, index) => `
        <tr>
            <td>${escapeHtml(product.product_name || product.stock_code || `产品 ${index + 1}`)}</td>
            <td>
                <div class="ratio-input-cell">
                    <input class="form-control form-control-sm ratio-input" type="number" min="0" step="0.0001" data-index="${index}" value="${escapeHtml(product.ratio || 0)}">
                    <span class="input-group-text">%</span>
                </div>
            </td>
            <td><span class="ratio-status-text">${Number(product.ratio || 0) > 0 ? "参与计算" : "比例为 0，不参与组合与展示"}</span></td>
        </tr>
    `,
    )
    .join("");
  updateRatioStatus();
}

function formatRatioHeader(value) {
  const text = String(value == null ? "" : value).trim();
  if (!text) {
    return "-";
  }
  return text.endsWith("%") ? text : `${text}%`;
}

function collectRatioValues() {
  return Array.from(document.querySelectorAll(".ratio-input")).map((input) =>
    Number(input.value || 0),
  );
}

function normalizeRatioForSignature(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? String(Number(number.toFixed(8))) : "NaN";
}

function ratioSignatureFromValues(values) {
  return values.map(normalizeRatioForSignature).join("|");
}

function ratioSignatureFromProducts(products) {
  return ratioSignatureFromValues(
    (products || []).map((product) => product.ratio),
  );
}

function currentRatioSignature() {
  return ratioSignatureFromValues(collectRatioValues());
}

async function applyRatioPreview() {
  const ratios = collectRatioValues();
  if (ratios.some((value) => !Number.isFinite(value) || value < 0)) {
    alert("产品比例必须是大于等于 0 的数字");
    return;
  }
  if (!previewPayload) {
    return;
  }
  const signature = ratioSignatureFromValues(ratios);
  if (signature === appliedRatioSignature) {
    ratioInputsDirty = false;
    updateRatioStatus();
    alert("比例未变化，无需重新计算");
    return;
  }

  const button = document.getElementById("calculateRatiosBtn");
  button.disabled = true;
  try {
    previewPayload = await Api.endpoints.backtestMulti.calculateRatios(
      encodeURIComponent(TASK_ID),
      {
        ratios: ratios.map((ratio, index) => ({ product_index: index, ratio })),
      },
    );
    hasUnsavedRatioPreview = true;
    ratioInputsDirty = false;
    appliedRatioSignature = signature;
    renderSummary();
    renderGroupOptions();
    renderRatios();
    renderActiveGroup();
  } catch (error) {
    alert(error.message || "计算失败");
  } finally {
    button.disabled = false;
  }
}

function renderActiveGroup() {
  const container = document.getElementById("previewContainer");
  const groups = Array.isArray(previewPayload?.groups)
    ? previewPayload.groups
    : [];
  const products = Array.isArray(previewPayload?.products)
    ? previewPayload.products
    : [];
  const group = groups.find((item) => item.group_key === activeGroupKey);
  if (!group) {
    container.innerHTML =
      '<div class="empty-state">当前没有可展示的参数方案</div>';
    return;
  }
  if (!Array.isArray(group.rows) || !group.rows.length) {
    container.innerHTML =
      '<div class="empty-state">该参数方案下没有成功结果</div>';
    return;
  }
  // 比例为 0 的产品不参与组合，展示全 0 列没有意义，直接不渲染其列组。
  const visibleProducts = products
    .map((product, index) => ({ product, index }))
    .filter((item) => Number(item.product.ratio || 0) > 0);
  if (!visibleProducts.length) {
    container.innerHTML =
      '<div class="empty-state">所有产品比例均为 0，没有可展示的产品</div>';
    return;
  }
  const productHeads = visibleProducts
    .map(({ product }) => {
      const name = product.product_name || product.stock_code || "产品";
      return `
            <td colspan="3">${escapeHtml(name)}</td>
        `;
    })
    .join("");
  const columnHeads = visibleProducts
    .map(
      ({ product }) => `
        <th>指数</th>
        <th>模型结果</th>
        <th>模型结果（${escapeHtml(formatRatioHeader(product.ratio || 0))}）</th>
    `,
    )
    .join("");
  const body = group.rows
    .map((row) => {
      const values = visibleProducts
        .map(({ index }) => {
          const item = (row.product_values || [])[index] || {};
          return `
            <td>${escapeHtml(item.index_value || "-")}</td>
            <td>${escapeHtml(item.result_value || "-")}</td>
            <td>${escapeHtml(item.weighted_result_value || "-")}</td>
        `;
        })
        .join("");
      return `
            <tr>
                <td class="sticky-col sticky-col-1 fw-semibold">${escapeHtml(row.category || "-")}</td>
                <td class="sticky-col sticky-col-2">${escapeHtml(row.metric || "-")}</td>
                ${values}
                <td class="fw-semibold">${escapeHtml(row.weighted_index_value || "-")}</td>
                <td class="fw-semibold">${escapeHtml(row.weighted_result_value || "-")}</td>
            </tr>
        `;
    })
    .join("");
  container.innerHTML = `
        <table class="table table-bordered align-middle preview-table">
            <thead>
                <tr class="product-title-row">
                    <td class="sticky-col sticky-col-1"></td>
                    <td class="sticky-col sticky-col-2"></td>
                    ${productHeads}
                    <td colspan="2"></td>
                </tr>
                <tr class="column-title-row">
                    <th class="sticky-col sticky-col-1">指标类型</th>
                    <th class="sticky-col sticky-col-2">指标</th>
                    ${columnHeads}
                    <th>比例计算-指数</th>
                    <th>比例计算-结果</th>
                </tr>
            </thead>
            <tbody>${body}</tbody>
        </table>
    `;
}

async function loadGlobalPreview() {
  const container = document.getElementById("previewContainer");
  try {
    previewPayload = await Api.endpoints.backtestMulti.globalPreview(
      encodeURIComponent(TASK_ID),
    );
    hasUnsavedRatioPreview = false;
    ratioInputsDirty = false;
    appliedRatioSignature = ratioSignatureFromProducts(
      previewPayload.products || [],
    );
    activeGroupKey =
      previewPayload.groups && previewPayload.groups.length
        ? previewPayload.groups[0].group_key
        : "";
    // 在首次渲染前应用跳转携带的比例，避免先展示原比例再跳变
    const ratiosApplied = takeRatiosFromUrlQuery();
    renderSummary();
    renderGroupOptions();
    renderRatios();
    if (ratiosApplied) {
      ratioInputsDirty = currentRatioSignature() !== appliedRatioSignature;
      updateRatioStatus();
      // 展开比例设置面板，让用户直接看到填充结果
      const ratioPanel = document.getElementById("ratioPanel");
      if (ratioPanel) {
        ratioPanel.open = true;
      }
      if (ratioInputsDirty) {
        // 携带的比例与已保存不同：先算完再渲染指标表，期间不展示按原比例算出的数据
        container.innerHTML =
          '<div class="empty-state">正在按携带的比例计算预览...</div>';
        await applyRatioPreview();
        if (!container.querySelector(".preview-table")) {
          // 计算失败时给出明确提示（applyRatioPreview 内部已 alert），避免停留在加载文案
          container.innerHTML =
            '<div class="empty-state">比例预览计算失败，请点击“计算预览”重试</div>';
        }
      } else {
        // 携带的比例与已保存一致，无需重新计算
        renderActiveGroup();
      }
    } else {
      renderActiveGroup();
    }
  } catch (error) {
    container.innerHTML = `<div class="empty-state text-danger">${escapeHtml(error.message || "加载失败")}</div>`;
  }
}

// 支持从权重组合分析页“查看”跳转：URL 携带 ratios=[{stock_code, ratio}]，
// 按 stock_code 匹配产品改写 payload 比例（组合外产品归 0）。
// 必须在首次渲染前调用，返回是否应用了参数。
function takeRatiosFromUrlQuery() {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("ratios");
  if (!raw) {
    return false;
  }
  let entries = [];
  try {
    entries = JSON.parse(raw);
  } catch (error) {
    console.warn("ratios 参数解析失败", error);
    return false;
  }
  if (!Array.isArray(entries) || !entries.length) {
    return false;
  }
  const ratioByCode = new Map(
    entries
      .filter((item) => item && item.stock_code != null)
      .map((item) => [String(item.stock_code), Number(item.ratio) || 0]),
  );
  if (!ratioByCode.size) {
    return false;
  }
  const products = Array.isArray(previewPayload.products)
    ? previewPayload.products
    : [];
  const matched = products.some((product) =>
    ratioByCode.has(String(product.stock_code || "")),
  );
  if (!matched) {
    console.warn("ratios 参数未匹配到任何产品，忽略");
    return false;
  }
  products.forEach((product) => {
    const ratio = ratioByCode.get(String(product.stock_code || ""));
    product.ratio = ratio === undefined ? 0 : ratio;
  });
  // 用完即清，避免刷新后再次覆盖用户手动输入
  const url = new URL(window.location.href);
  url.searchParams.delete("ratios");
  window.history.replaceState({}, "", url);
  return true;
}

async function saveRatios() {
  if (ratioInputsDirty) {
    alert("比例已修改，请先点击“计算预览”确认结果，再保存比例。");
    return;
  }
  const ratios = Array.from(document.querySelectorAll(".ratio-input")).map(
    (input) => ({
      product_index: Number(input.dataset.index),
      ratio: input.value,
    }),
  );
  if (
    ratios.some((item) => {
      const value = Number(item.ratio);
      return !Number.isFinite(value) || value < 0;
    })
  ) {
    alert("产品比例必须是大于等于 0 的数字");
    return;
  }
  const button = document.getElementById("saveRatiosBtn");
  button.disabled = true;
  try {
    previewPayload = await Api.endpoints.backtestMulti.updateRatios(
      encodeURIComponent(TASK_ID),
      { ratios },
    );
    hasUnsavedRatioPreview = false;
    ratioInputsDirty = false;
    appliedRatioSignature = ratioSignatureFromProducts(
      previewPayload.products || [],
    );
    renderSummary();
    renderGroupOptions();
    renderRatios();
    renderActiveGroup();
  } catch (error) {
    alert(error.message || "保存失败");
  } finally {
    button.disabled = false;
  }
}

async function exportPreview() {
  let exportQuery = "";
  if (hasUnsavedRatioPreview && !ratioInputsDirty) {
    const ratios = collectRatioValues().map((ratio, index) => ({
      product_index: index,
      ratio,
    }));
    exportQuery = `?ratios=${encodeURIComponent(JSON.stringify(ratios))}`;
  }
  const response = await Api.endpoints.export.globalPreview(
    encodeURIComponent(TASK_ID),
    exportQuery,
  );
  if (!response.ok) {
    alert("导出失败");
    return;
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = buildExcelDownloadName();
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

// ===== 导出收益序列（Biz 公共组件：后端纯数据，Excel 公式自动计算） =====

function exportReturnSeries() {
  if (!activeGroupKey) {
    alert("当前没有可导出的参数方案");
    return;
  }
  Biz.returnSeriesExport
    .exportAndDownload({
      taskId: TASK_ID,
      taskName: () => previewPayload?.task?.name || TASK_ID,
      groupKey: () => activeGroupKey,
      // 组合公式按当前页面比例写权重；页面不传时后端用任务默认比例。
      ratios: () =>
        collectRatioValues().map((ratio, index) => ({
          product_index: index,
          ratio,
        })),
    })
    .catch((error) => alert(error.message || "导出失败"));
}

// async function exportWordReport() {
//     if (!previewPayload || !activeGroupKey) {
//         alert('当前没有可导出的参数方案');
//         return;
//     }
//     if (ratioInputsDirty) {
//         alert('比例已修改，请先点击“计算预览”确认结果，再导出 Word。');
//         return;
//     }

//     const button = document.getElementById('exportWordBtn');
//     button.disabled = true;
//     try {
//         const ratios = collectRatioValues().map((ratio, index) => ({ product_index: index, ratio }));
//         const response = await Api.endpoints.export.wordReport({
//             report_type: 'RPT-M',
//             task_id: TASK_ID,
//             group_key: activeGroupKey,
//             ratios
//         });
//         if (!response.ok) {
//             const data = await response.json().catch(() => ({}));
//             throw new Error(data.message || 'Word 导出失败');
//         }
//         const filename = response.headers.get('Content-Disposition')
//             ?.match(/filename[^;=\n]*=(?:UTF-8''|\")?([^;\n\"]+)/i)?.[1]
//             || 'RPT-M.docx';
//         const link = document.createElement('a');
//         const objectUrl = URL.createObjectURL(await response.blob());
//         link.href = objectUrl;
//         link.download = decodeURIComponent(filename.replace(/^\"|\"$/g, ''));
//         document.body.appendChild(link);
//         link.click();
//         link.remove();
//         URL.revokeObjectURL(objectUrl);
//     } catch (error) {
//         alert(error.message || 'Word 导出失败');
//     } finally {
//         button.disabled = false;
//     }
// }


// ===== 导出 Word 选股票弹窗（多选+比例；组合指数是否并列由开关控制，默认开启） =====
// 语义 A：每个基准条目 = {code, ratio}，基准序列按 比例×指数日收益+现金 缩放；
// 同一产品可用不同比例添加多条（如 QQQ 50% 与 QQQ 100% 两条基准列）。
const benchmarkEntries = [];
const DEFAULT_BENCHMARK_RATIO = 100;

// 组合指数开关：默认开启；开启时全部产品按比例组合为一个基准列，列头固定"指数"。
function includeCompositeEnabled() {
    const toggle = document.getElementById('includeCompositeBenchmark');
    return !toggle || toggle.checked;
}

// 价格类型取值 → 报告"价格类型"展示行文案（与后端 get_price_type 一致）。
const EXPORT_WORD_PRICE_TYPE_LABELS = {
    kp_price: '开盘价',
    sp_price: '收盘价',
    vwap_price: '加权平均价',
    ohlc_price: 'OHLC（开高低收）',
    random_price: '随机价',
};

// 读取弹窗配置：无风险利率按百分比填写（如 3 = 3%），payload 统一转小数
// （0.03）双通道（metadata 展示 + runtime_params 重算）；价格类型仅展示，
// 留空表示跟随任务配置。非法输入抛错交由调用方 alert。
function readExportWordOptions() {
    const raw = document.getElementById('export-word-risk-free-rate')?.value?.trim();
    let percent = 0;
    if (raw !== '' && raw !== undefined) {
        percent = Number(raw);
        if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
            throw new Error('无风险利率需为 0～100 之间的数字（百分比）');
        }
    }
    const priceValue = document.getElementById('export-word-price-type')?.value || '';
    return {
        metadata: {
            ...(priceValue ? { price_type: EXPORT_WORD_PRICE_TYPE_LABELS[priceValue] } : {}),
            risk_free_rate: `${percent.toFixed(2)}%`,
        },
        runtime_params: { risk_free_rate: percent / 100 },
    };
}

// ---- 公共导出函数（不弹窗时也用它）----
async function exportWordDirectly(benchmarks) {
    try {
        const ratios = collectRatioValues().map((ratio, index) => ({ product_index: index, ratio }));
        const payload = {
            report_type: 'RPT-M',
            task_id: TASK_ID,
            group_key: activeGroupKey,
            ratios,
            include_composite_benchmark: includeCompositeEnabled(),
        };
        if (Array.isArray(benchmarks) && benchmarks.length) {
            payload.index_benchmarks = benchmarks;
        }
        // 弹窗配置随请求透传：后端把请求 metadata/runtime_params 覆盖到按
        // 任务重建的载荷上（价格类型展示行 + 无风险利率重算）。
        Object.assign(payload, readExportWordOptions());

        const response = await Api.endpoints.export.wordReport(payload);

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.message || 'Word 导出失败');
        }

        const filename = response.headers.get('Content-Disposition')
            ?.match(/filename[^;=\n]*=(?:UTF-8''|")?([^;\n"]+)/i)?.[1]
            || `RPT-M_${(benchmarks || []).map(b => `${b.stock_code}${Number(b.ratio) === 100 ? '' : Number(b.ratio)}`).join('_') || 'all'}.docx`;

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = decodeURIComponent(filename.replace(/^"|"$/g, ''));
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        alert(err.message || 'Word 导出失败');
    }
}

// ---- 打开弹窗（或直接导出）----
function openExportWordModal() {
    if (ratioInputsDirty) {
        alert('比例已修改，请先点击“计算预览”确认结果，再导出 Word。');
        return;
    }
    if (!previewPayload || !activeGroupKey) {
        alert('当前没有可导出的参数方案');
        return;
    }

    // // ✅ 比例 > 0 的股票少于 2 个时，不弹窗，直接导出全部
    // const products = Array.isArray(previewPayload?.products) ? previewPayload.products : [];
    // const activeCount = products.filter(p => Number(p.ratio || 0) > 0).length;
    // if (activeCount < 2) {
    //     exportWordDirectly('');
    //     return;
    // }

    benchmarkEntries.length = 0;
    renderSelectedBenchmarks();
    renderStockList();
    new bootstrap.Modal(document.getElementById('exportWordModal')).show();
}

// ---- 股票列表 ----
function getStockOptions() {
    const products = Array.isArray(previewPayload?.products) ? previewPayload.products : [];
    return products
        .map((p, i) => ({
            index: i,
            name: p.product_name || `产品${i + 1}`,
            code: p.stock_code || '',
            ratio: Number(p.ratio || 0)
        }))
        .filter(s => s.code);
}

function stockEntryCount(code) {
    return benchmarkEntries.filter(entry => entry.code === code).length;
}

function renderStockList() {
    const list = getStockOptions();
    const container = document.getElementById('stockListContainer');
    const counter = document.getElementById('stockSelectedCount');
    if (counter) {
        counter.textContent = `已选 ${benchmarkEntries.length} 条`;
    }

    let html = `
        <div class="stock-option-row stock-default-row">
            <span class="flex-grow-1 text-body-secondary">组合指数由上方开关控制；未选股票时始终包含组合指数</span>
        </div>
    `;

    if (!list.length) {
        html += '<div class="text-center text-body-secondary py-3">暂无可选股票</div>';
        container.innerHTML = html;
        return;
    }

    html += list.map(s => {
        const count = stockEntryCount(s.code);
        return `
            <div class="stock-option-row stock-add-row ${count ? 'is-selected' : ''}"
                 data-code="${escapeHtml(s.code)}" title="点击添加为基准；再次点击可用不同比例叠加">
                <span class="flex-grow-1 stock-name-text">${escapeHtml(s.name)} <span class="text-body-secondary">(${escapeHtml(s.code)})</span></span>
                ${count ? `<span class="badge text-bg-info">×${count}</span>` : ''}
                <small class="text-body-secondary">比例 ${s.ratio}%</small>
                <i class="bi bi-plus-circle-fill stock-add-icon"></i>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
    container.querySelectorAll('.stock-add-row').forEach(row => {
        row.addEventListener('click', () => addBenchmark(row.dataset.code));
    });
}

function addBenchmark(code) {
    benchmarkEntries.push({ code, ratio: DEFAULT_BENCHMARK_RATIO });
    renderSelectedBenchmarks();
    renderStockList();
}

function removeBenchmark(index) {
    benchmarkEntries.splice(index, 1);
    renderSelectedBenchmarks();
    renderStockList();
}

function renderSelectedBenchmarks() {
    const container = document.getElementById('selectedBenchmarks');
    if (!container) {
        return;
    }
    if (!benchmarkEntries.length) {
        container.innerHTML = '<div class="selected-empty">未选择自定义指数（点击下方股票添加）；组合指数由上方开关控制</div>';
        return;
    }
    container.innerHTML = benchmarkEntries.map((entry, index) => `
        <div class="selected-benchmark-row">
            <span class="selected-code flex-grow-1">${escapeHtml(entry.code)}</span>
            <input type="number" class="form-control form-control-sm benchmark-ratio-input"
                   min="0.5" max="100" step="0.5" value="${entry.ratio}"
                   data-index="${index}" aria-label="基准比例">
            <span class="ratio-unit">%</span>
            <button type="button" class="btn-close btn-sm" data-remove="${index}" aria-label="删除该基准"></button>
        </div>
    `).join('');
    container.querySelectorAll('.benchmark-ratio-input').forEach(input => {
        input.addEventListener('change', e => {
            const index = Number(e.target.dataset.index);
            const value = Number(e.target.value);
            // 比例语义为 (0, 100]，非法输入回退默认 100；后端 Schema 兜底校验。
            benchmarkEntries[index].ratio = Number.isFinite(value) && value > 0
                ? Math.min(value, 100)
                : DEFAULT_BENCHMARK_RATIO;
            e.target.value = benchmarkEntries[index].ratio;
        });
    });
    container.querySelectorAll('[data-remove]').forEach(btn => {
        btn.addEventListener('click', () => removeBenchmark(Number(btn.dataset.remove)));
    });
}

// ---- 确认导出 ----
document.getElementById('confirmExportWordBtn')?.addEventListener('click', async function () {
    const btn = this;
    btn.disabled = true;
    const original = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>导出中...';

    try {
        await exportWordDirectly(benchmarkEntries.map(entry => ({
            stock_code: entry.code,
            ratio: Number(entry.ratio) || DEFAULT_BENCHMARK_RATIO,
        })));
        bootstrap.Modal.getInstance(document.getElementById('exportWordModal'))?.hide();
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
    }
});


document.getElementById("groupSelect").addEventListener("change", (event) => {
  activeGroupKey = event.target.value;
  renderActiveGroup();
});
document.getElementById("ratioListBody").addEventListener("input", () => {
  ratioInputsDirty = currentRatioSignature() !== appliedRatioSignature;
  updateRatioStatus();
});
document
  .getElementById("calculateRatiosBtn")
  .addEventListener("click", applyRatioPreview);
document.getElementById("saveRatiosBtn").addEventListener("click", saveRatios);
document.getElementById("exportBtn").addEventListener("click", exportPreview);
document
  .getElementById("exportSeriesBtn")
  .addEventListener("click", exportReturnSeries);
// document.getElementById('exportWordBtn').addEventListener('click', exportWordReport);
document
  .getElementById("exportWordBtn")
  .addEventListener("click", openExportWordModal);
loadGlobalPreview();
