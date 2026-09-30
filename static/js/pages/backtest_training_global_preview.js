
    const TASK_ID = (window.location.pathname.match(/\/global-preview\/([^/]+)/) || [])[1] || '';
    // 静态化（03 §3 #1）：原服务端注入的 summaryTaskId/backToDetailLink task_id 改为运行时填充
    //（backToDetailLink 之后仍由 DOMContentLoaded 的 buildDetailHref 附加分页状态参数）
    (function () {
        const summaryTaskIdEl = document.getElementById('summaryTaskId');
        if (summaryTaskIdEl) {
            summaryTaskIdEl.textContent = TASK_ID;
        }
        const backToDetailLinkEl = document.getElementById('backToDetailLink');
        if (backToDetailLinkEl) {
            backToDetailLinkEl.href = '/backtest-training/detail/' + encodeURIComponent(TASK_ID);
        }
    })();
    let previewPayload = null;
    let activeGroupKey = null;

    document.addEventListener('DOMContentLoaded', () => {
        const backToDetailLink = document.getElementById('backToDetailLink');
        if (backToDetailLink) {
            backToDetailLink.href = buildDetailHref();
        }
        loadGlobalPreview();
        document.getElementById('exportGlobalPreviewBtn')?.addEventListener('click', exportGlobalPreview);
        document.getElementById('exportSeriesBtn')?.addEventListener('click', exportReturnSeries);
        document.getElementById('exportWordBtn')?.addEventListener('click', openExportWordModal);
        document.getElementById('confirmExportWordBtn')?.addEventListener('click', confirmExportWord);
        document.getElementById('groupSelect')?.addEventListener('change', (event) => {
            activeGroupKey = event.target.value;
            renderActiveGroup();
        });
    });

    function buildDetailHref() {
        const currentParams = new URLSearchParams(window.location.search);
        const detailParams = new URLSearchParams();
        ['list_page', 'list_per_page', 'result_page', 'result_per_page'].forEach((key) => {
            const value = currentParams.get(key);
            if (value) {
                detailParams.set(key, value);
            }
        });
        const query = detailParams.toString();
        return `/backtest-training/detail/${encodeURIComponent(TASK_ID)}${query ? `?${query}` : ''}`;
    }

    async function loadGlobalPreview() {
        const container = document.getElementById('previewContainer');
        try {
            previewPayload = await Api.endpoints.backtest.globalPreview(encodeURIComponent(TASK_ID));
            activeGroupKey = previewPayload.groups && previewPayload.groups.length ? previewPayload.groups[0].group_key : '';
            renderSummary();
            renderGroupOptions();
            renderActiveGroup();
        } catch (error) {
            container.innerHTML = `<div class="empty-state text-danger">${escapeHtml(error.message || '加载失败')}</div>`;
        }
    }

    // 导出收益序列（Biz 公共组件：后端纯数据，Excel 公式自动计算）。
    // 单品任务没有参数方案比例，导出该任务下全部收益序列（每条一个 sheet）。
    function exportReturnSeries() {
        Biz.returnSeriesExport
            .exportAndDownload({
                taskId: TASK_ID,
                taskName: () => previewPayload?.task?.name || TASK_ID,
                groupKey: null,
                ratios: null,
            })
            .catch((error) => alert(error.message || '导出失败'));
    }

    // ===== 导出 Word（RPT-S）：弹窗选择导出哪个参数的结果 =====
    // 价格类型取值 ↔ 报告展示文案（与后端 get_price_type 一致，同训练结果页弹窗）。
    const WORD_PRICE_TYPE_LABELS = {
        kp_price: '开盘价',
        sp_price: '收盘价',
        vwap_price: '加权平均价',
        ohlc_price: 'OHLC（开高低收）',
        random_price: '随机价'
    };

    // 可导出列 = 当前分组下成功且后端附带 RPT-S 请求载荷的结果列。
    function exportableWordColumns() {
        const groups = Array.isArray(previewPayload?.groups) ? previewPayload.groups : [];
        const group = groups.find((item) => item.group_key === activeGroupKey);
        const columns = Array.isArray(group?.columns) ? group.columns : [];
        return columns.filter((column) => column.success && column.word_report_payload);
    }

    function openExportWordModal() {
        const exportable = exportableWordColumns();
        if (!exportable.length) {
            alert('当前分组没有可导出的参数结果（需要成功且带收益序列）');
            return;
        }
        renderWordExportParamList(exportable);
        const rateInput = document.getElementById('word-export-risk-free-rate');
        if (rateInput) rateInput.value = '0';
        const priceSelect = document.getElementById('word-export-price-type');
        if (priceSelect) priceSelect.value = '';
        bootstrap.Modal.getOrCreateInstance(document.getElementById('exportWordModal')).show();
    }

    function renderWordExportParamList(columns) {
        const container = document.getElementById('wordExportParamList');
        container.innerHTML = columns.map((column, index) => `
            <div class="form-check">
                <input class="form-check-input" type="radio" name="wordExportParam"
                       id="wordExportParam${escapeHtml(String(column.result_id))}"
                       value="${escapeHtml(String(column.result_id))}" ${index === 0 ? 'checked' : ''}>
                <label class="form-check-label" for="wordExportParam${escapeHtml(String(column.result_id))}">
                    ${escapeHtml(column.header || `结果 ${column.result_id}`)}
                    <span class="text-body-secondary small">（结果 ID: ${escapeHtml(String(column.result_id))}）</span>
                </label>
            </div>
        `).join('');
    }

    async function confirmExportWord() {
        const selectedId = document.querySelector('input[name="wordExportParam"]:checked')?.value;
        if (!selectedId) {
            alert('请先选择要导出的参数结果');
            return;
        }
        const column = exportableWordColumns()
            .find((item) => String(item.result_id) === String(selectedId));
        const basePayload = column?.word_report_payload;
        if (!basePayload) {
            alert('所选参数结果没有可导出的收益序列');
            return;
        }

        // 无风险利率按百分比填写（如 3 = 3%），payload 统一转小数（0.03），
        // 双通道写入（metadata 展示 + runtime_params 重算），同训练结果页导出弹窗。
        let riskFreePercent = 0;
        const raw = document.getElementById('word-export-risk-free-rate')?.value?.trim();
        if (raw !== '' && raw !== undefined) {
            riskFreePercent = Number(raw);
            if (!Number.isFinite(riskFreePercent) || riskFreePercent < 0 || riskFreePercent > 100) {
                alert('无风险利率需为 0～100 之间的数字（百分比）');
                return;
            }
        }

        const btn = document.getElementById('confirmExportWordBtn');
        btn.disabled = true;
        const original = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>导出中...';

        try {
            const payload = JSON.parse(JSON.stringify(basePayload));
            payload.metadata = {
                ...(payload.metadata || {}),
                risk_free_rate: `${riskFreePercent.toFixed(2)}%`,
            };
            // 价格类型仅覆盖报告展示行；"跟随任务（默认）"保留 payload 原值。
            const priceValue = document.getElementById('word-export-price-type')?.value || '';
            if (priceValue) {
                payload.metadata.price_type = WORD_PRICE_TYPE_LABELS[priceValue];
            }
            payload.runtime_params = {
                ...(payload.runtime_params || {}),
                risk_free_rate: riskFreePercent / 100,
            };

            const response = await Api.endpoints.export.wordReport(payload);
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.message || 'Word 导出失败');
            }
            const filename = response.headers.get('Content-Disposition')
                ?.match(/filename[^;=\n]*=(?:UTF-8''|")?([^;\n"]+)/i)?.[1]
                || 'RPT-S.docx';
            const objectUrl = URL.createObjectURL(await response.blob());
            const link = document.createElement('a');
            link.href = objectUrl;
            link.download = decodeURIComponent(filename.replace(/^"|"$/g, ''));
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(objectUrl);
            bootstrap.Modal.getInstance(document.getElementById('exportWordModal'))?.hide();
        } catch (error) {
            alert(error.message || 'Word 导出失败');
        } finally {
            btn.disabled = false;
            btn.innerHTML = original;
        }
    }

    async function exportGlobalPreview() {
        const button = document.getElementById('exportGlobalPreviewBtn');
        const originalHtml = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>导出中';

        try {
            const response = await Api.endpoints.export.globalPreview(encodeURIComponent(TASK_ID));
            if (!response.ok) {
                const text = await response.text();
                let message = '导出失败';
                try {
                    const payload = JSON.parse(text);
                    message = payload.message || message;
                } catch (_error) {
                    message = text || message;
                }
                throw new Error(message);
            }

            const blob = await response.blob();
            const disposition = response.headers.get('Content-Disposition') || '';
            const filename = resolveDownloadFilename(disposition, `${TASK_ID}_global_preview.xlsx`);
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            alert(error.message || '导出失败');
        } finally {
            button.disabled = false;
            button.innerHTML = originalHtml;
        }
    }

    function resolveDownloadFilename(contentDisposition, fallback) {
        const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
        if (encodedMatch) {
            try {
                return decodeURIComponent(encodedMatch[1]);
            } catch (_error) {
                return encodedMatch[1];
            }
        }

        const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
        return plainMatch ? plainMatch[1] : fallback;
    }

    function renderSummary() {
        const task = previewPayload.task || {};
        const summary = previewPayload.summary || {};
        document.getElementById('taskTitleText').textContent = `全局预览 · ${task.name || TASK_ID}`;
        document.getElementById('summaryTaskId').textContent = task.id || TASK_ID;
        document.getElementById('summaryTotal').textContent = summary.total_results ?? 0;
        document.getElementById('summarySuccess').textContent = summary.success_results ?? 0;
        document.getElementById('summaryGroups').textContent = summary.group_count ?? 0;
    }

    function renderGroupOptions() {
        const select = document.getElementById('groupSelect');
        const groups = Array.isArray(previewPayload.groups) ? previewPayload.groups : [];
        if (!groups.length) {
            select.innerHTML = '<option value="">暂无分组</option>';
            select.disabled = true;
            return;
        }

        select.disabled = false;
        select.innerHTML = groups.map((group) => `
            <option value="${escapeHtml(group.group_key)}" ${group.group_key === activeGroupKey ? 'selected' : ''}>
                ${escapeHtml(group.group_label)} (${group.column_count} 组参数)
            </option>
        `).join('');
    }

    function renderActiveGroup() {
        const container = document.getElementById('previewContainer');
        const meta = document.getElementById('groupMeta');
        const groups = Array.isArray(previewPayload?.groups) ? previewPayload.groups : [];
        const group = groups.find((item) => item.group_key === activeGroupKey);

        if (!group) {
            meta.innerHTML = '';
            container.innerHTML = '<div class="empty-state">当前没有可展示的分组数据</div>';
            return;
        }

        meta.innerHTML = `
            <span class="badge text-bg-primary">${escapeHtml(group.group_label)}</span>
            <span class="badge text-bg-light">区间：${escapeHtml(group.period || '-')}</span>
            <span class="badge text-bg-light">参数列数：${escapeHtml(group.column_count || 0)}</span>
            <span class="badge text-bg-light">失败结果：${escapeHtml(group.failed_results || 0)}</span>
        `;

        if (!Array.isArray(group.rows) || !group.rows.length || !Array.isArray(group.columns) || !group.columns.length) {
            container.innerHTML = '<div class="empty-state">该分组下没有成功结果</div>';
            return;
        }

        const headColumns = group.columns.map((column) => `
            <th class="table-col-head">
                <div class="fw-semibold">${escapeHtml(column.header || `结果 ${column.result_id}`)}</div>
                <div class="small text-body-secondary mt-1">结果 ID: ${escapeHtml(column.result_id)}</div>
            </th>
        `).join('');

        const bodyRows = group.rows.map((row) => {
            const valueColumns = group.columns.map((column) => `
                <td>${escapeHtml(row.values?.[column.column_key] || '-')}</td>
            `).join('');

            return `
                <tr>
                    <td class="sticky-col sticky-col-1 fw-semibold">${escapeHtml(row.category || '-')}</td>
                    <td class="sticky-col sticky-col-2">${escapeHtml(row.metric || '-')}</td>
                    <td class="sticky-col sticky-col-3 text-body-secondary">${escapeHtml(row.index_value || '-')}</td>
                    ${valueColumns}
                </tr>
            `;
        }).join('');

        container.innerHTML = `
            <table class="table table-bordered align-middle preview-table">
                <thead>
                    <tr>
                        <th class="sticky-col sticky-col-1">指标类型</th>
                        <th class="sticky-col sticky-col-2">指标</th>
                        <th class="sticky-col sticky-col-3">指数</th>
                        ${headColumns}
                    </tr>
                </thead>
                <tbody>${bodyRows}</tbody>
            </table>
        `;
    }

