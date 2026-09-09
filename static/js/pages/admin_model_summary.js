// 页面脚本（templates/admin/model_summary.html 内联脚本原样抽离，F5 de-jinja）。
    const state = {
        page: 1,
        perPage: 50,
        columns: [],
        total: 0,
        pages: 0,
        summary: {},
        rebuildJobId: "",
        rebuildTimer: null,
    };

    const leadingColumns = [
        ["stock_code", "产品/股票"],
        ["stock_name", "股票名"],
        ["task_name", "任务名"],
        ["task_type", "类型"],
        ["best_metric_value", "return beats"],
        ["result_timestamp", "结果时间"],
    ];

    const trailingColumns = [
        ["task_result_id", "结果 ID"],
    ];

    function getToken() {
        return localStorage.getItem("access_token") || "";
    }

    function formatMetric(value, format) {
        if (value === null || value === undefined || value === "") return "-";
        const number = Number(value);
        if (!Number.isFinite(number)) return String(value);
        if (format === "percent") return `${(number * 100).toFixed(2)}%`;
        if (format === "integer") return String(Math.round(number));
        return number.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
    }

    function metricClass(value) {
        const number = Number(value);
        if (!Number.isFinite(number) || number === 0) return "";
        return number > 0 ? "metric-positive" : "metric-negative";
    }

    function taskTypeLabel(value) {
        return {
            google_sheet: "C3",
            google_sheet_C4: "C4",
            google_sheet_C5: "C5",
            backtest_training: "回测",
        }[value] || value || "-";
    }

    function periodFilterLabel(value) {
        return {
            recent_1y: "近1年",
            recent_3y: "近3年",
            full_2026: "整年26",
            full_2025: "整年25",
            full_2024: "整年24",
            full_2023: "整年23",
            full_2022: "整年22",
            full_2021: "整年21",
            full_2020: "整年20",
            full_2019: "整年19",
        }[value] || "";
    }

    function normalizeTaskType(value) {
        return String(value || "").trim().toLowerCase();
    }

    function getTaskVersionFromType(taskType) {
        const normalized = normalizeTaskType(taskType);
        if (normalized === "google_sheet_c4") return "c4";
        if (normalized === "google_sheet_c5") return "c5";
        return "";
    }

    function buildTaskDetailUrl(item) {
        const taskId = item?.task_id || "";
        if (!taskId) return "";
        const normalized = normalizeTaskType(item.task_type);
        if (normalized === "backtest_training") {
            return `/backtest-training/detail/${encodeURIComponent(taskId)}`;
        }
        const params = new URLSearchParams({ task_id: taskId });
        const taskVersion = getTaskVersionFromType(item.task_type);
        if (taskVersion) params.set("version", taskVersion);
        return `/google-sheet/detail?${params.toString()}`;
    }

    function renderTaskName(item) {
        const label = item.task_name || item.task_id || "-";
        const href = buildTaskDetailUrl(item);
        const title = item.task_id ? `${label} (${item.task_id})` : label;
        if (!href) return `<span title="${escapeHtml(title)}">${escapeHtml(label)}</span>`;
        return `<a class="task-link" href="${href}" title="${escapeHtml(title)}">${escapeHtml(label)}</a>`;
    }

    function formatDateTime(value) {
        if (!value) return "-";
        const text = String(value).replace("T", " ");
        const [date = "", timeWithZone = ""] = text.split(" ");
        const time = timeWithZone.replace(/\.\d+$/, "").slice(0, 8);
        if (!date && !time) return escapeHtml(value);
        return `
            <span class="time-stack" title="${escapeHtml(text)}">
                <span class="date">${escapeHtml(date || "-")}</span>
                <span class="time">${escapeHtml(time || "-")}</span>
            </span>
        `;
    }

    function formatParameterValue(value) {
        if (Array.isArray(value)) return value.join(", ");
        if (value && typeof value === "object") return JSON.stringify(value);
        return String(value ?? "");
    }

    function renderParameterTags(parameterSummary) {
        if (!parameterSummary || typeof parameterSummary !== "object" || Array.isArray(parameterSummary)) {
            return `<span class="text-muted">-</span>`;
        }
        const entries = Object.entries(parameterSummary).filter(([, value]) => value !== null && value !== undefined && value !== "");
        if (!entries.length) return `<span class="text-muted">-</span>`;
        return `<div class="param-tags">${entries.map(([key, value]) => {
            const displayValue = formatParameterValue(value);
            return `
                <span class="param-tag" title="${escapeHtml(key)}: ${escapeHtml(displayValue)}">
                    <span class="key">${escapeHtml(key)}</span>
                    <span class="value">${escapeHtml(displayValue)}</span>
                </span>
            `;
        }).join("")}</div>`;
    }

    function collectParams() {
        const params = new URLSearchParams({
            page: String(state.page),
            per_page: String(state.perPage),
            summary_type: document.getElementById("summaryType").value,
            best_only: document.getElementById("bestOnly").value,
        });
        const fields = [
            ["task_type", "taskType"],
            ["stock_code", "stockCode"],
            ["market_type", "marketType"],
            ["period_filter", "periodFilter"],
            ["excess_return_min", "excessReturnMin"],
            ["task_id", "taskId"],
            ["result_id", "resultId"],
        ];
        fields.forEach(([key, id]) => {
            const value = document.getElementById(id).value.trim();
            if (value) params.set(key, value);
        });

        // 添加日期范围参数
        const dateFrom = document.getElementById("resultDateFrom").value;
        const dateTo = document.getElementById("resultDateTo").value;
        if (dateFrom) params.set("result_date_from", dateFrom);
        if (dateTo) params.set("result_date_to", dateTo);

        return params;
    }

    function safeFilenamePart(value) {
        const text = String(value || "").trim();
        if (!text) return "";
        return text.replace(/[\\/:*?"<>|\r\n\t]+/g, "_").slice(0, 80);
    }

    function defaultExportFilename() {
        const summaryType = document.getElementById("summaryType").value === "stock" ? "股票汇总" : "任务汇总";
        const range = document.getElementById("bestOnly").value === "false" ? "全部结果" : "仅最优";
        const taskTypeValue = document.getElementById("taskType").value;
        const taskType = taskTypeValue ? taskTypeLabel(taskTypeValue) : "全部类型";
        const periodValue = document.getElementById("periodFilter").value;
        const periodText = periodValue ? periodFilterLabel(periodValue) : "";
        const threshold = document.getElementById("excessReturnMin").value;
        const keyword = document.getElementById("stockCode").value.trim() || document.getElementById("taskId").value.trim() || "全部";
        const now = new Date();
        const pad = (value) => String(value).padStart(2, "0");
        const timestamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
        return [summaryType, range, taskType, periodText, threshold ? `超额大于${threshold}` : "", keyword, timestamp]
            .map(safeFilenamePart)
            .filter(Boolean)
            .join("_");
    }

    function describeExportFilters() {
        const taskTypeValue = document.getElementById("taskType").value;
        const taskType = taskTypeValue ? taskTypeLabel(taskTypeValue) : "全部";
        const marketTypeValue = document.getElementById("marketType").value;
        const marketType = marketTypeValue === "cn" ? "A股" : (marketTypeValue === "us" ? "美股" : "全部市场");
        const periodValue = document.getElementById("periodFilter").value;
        const periodText = periodValue ? periodFilterLabel(periodValue) : "全部";
        const keyword = document.getElementById("stockCode").value.trim() || "未填写";
        const summaryType = document.getElementById("summaryType").value === "stock" ? "股票汇总" : "任务汇总";
        const range = document.getElementById("bestOnly").value === "false" ? "全部结果" : "仅最优";
        const threshold = document.getElementById("excessReturnMin").value;
        const thresholdText = threshold ? `ReturnBeats > ${threshold}%` : "全部";
        // 添加日期范围描述
        const dateFrom = document.getElementById("resultDateFrom").value;
        const dateTo = document.getElementById("resultDateTo").value;
        let dateRangeText = "";
        if (dateFrom && dateTo) {
            dateRangeText = `；结果日期：${dateFrom} 至${dateTo}`;
        } else if (dateFrom) {
            dateRangeText = `；结果日期：≥ ${dateFrom}`;
        } else if (dateTo) {
            dateRangeText = `；结果日期：≤ ${dateTo}`;
        }

        return `任务类型：${taskType}；市场：${marketType}；年份 / 区间：${periodText}；查询词：${keyword}；汇总方式：${summaryType}；数据范围：${range}；超额收益：${thresholdText}${dateRangeText}`;
    }

    function renderHead() {
        const fixedHead = leadingColumns.map(([key, label], index) => {
            const sticky = index === 0 ? ` sticky-col sticky-col-${index + 1}` : "";
            return `<th class="${sticky}">${label}</th>`;
        }).join("");
        const metricHead = state.columns.map((column) => `<th>${column.label}</th>`).join("");
        const trailingHead = trailingColumns.map(([, label]) => `<th>${label}</th>`).join("");
        document.getElementById("summaryHead").innerHTML = `<tr>${fixedHead}<th>参数</th><th>年份/区间</th>${metricHead}${trailingHead}</tr>`;
    }

    function renderBody(items) {
        const body = document.getElementById("summaryBody");
        if (!items.length) {
            body.innerHTML = `<tr><td colspan="${leadingColumns.length + state.columns.length + trailingColumns.length + 2}" class="text-center text-muted py-5">暂无汇总数据，请先重建索引或调整筛选条件</td></tr>`;
            return;
        }
        body.innerHTML = items.map((item) => {
            const renderTextValue = (value) => value === null || value === undefined || value === "" ? "-" : escapeHtml(value);
            const leadingCells = leadingColumns.map(([key], index) => {
                const sticky = index === 0 ? ` sticky-col sticky-col-${index + 1}` : "";
                let value = item[key];
                if (key === "task_type") value = taskTypeLabel(value);
                if (key === "best_metric_value") value = formatMetric(value, "percent");
                if (key === "task_name") value = renderTaskName(item);
                if (key === "result_timestamp") value = formatDateTime(value);
                if (key === "task_result_id") value = `<a href="/admin/results?task_id=${encodeURIComponent(item.task_id || "")}">${value || "-"}</a>`;
                if (key === "stock_name" && !value) value = "-";
                const klass = key === "best_metric_value" ? metricClass(item.best_metric_value) : "";
                const html = ["task_name", "result_timestamp", "task_result_id"].includes(key) ? (value || "-") : renderTextValue(value);
                return `<td class="${sticky} ${klass}">${html}</td>`;
            }).join("");
            const parameter = renderParameterTags(item.parameter_summary);
            const interval = renderTextValue(item.kline_range || item.year_label);
            const metrics = state.columns.map((column) => {
                const value = item.metrics ? item.metrics[column.key] : null;
                return `<td class="${metricClass(value)}">${escapeHtml(formatMetric(value, column.format))}</td>`;
            }).join("");
            const trailingCells = trailingColumns.map(([key]) => {
                let value = item[key];
                if (key === "task_type") value = taskTypeLabel(value);
                if (key === "task_result_id") value = `<a href="/admin/results?task_id=${encodeURIComponent(item.task_id || "")}">${value || "-"}</a>`;
                const html = key === "task_result_id" ? (value || "-") : renderTextValue(value);
                return `<td>${html}</td>`;
            }).join("");
            return `<tr>${leadingCells}<td>${parameter}</td><td>${interval}</td>${metrics}${trailingCells}</tr>`;
        }).join("");
    }

    function renderSummary(summary) {
        const data = summary || {};
        const setText = (id, value) => {
            document.getElementById(id).textContent = String(value ?? 0);
        };
        const stockCount = Number(data.stock_count || 0);
        const cnCount = Number(data.cn_stock_count || 0);
        const usCount = Number(data.us_stock_count || 0);
        const taskCount = Number(data.task_count || 0);
        const isStockSummary = document.getElementById("summaryType").value === "stock";
        const returnRateBase = isStockSummary ? stockCount : taskCount;
        const returnRateCaption = isStockSummary ? "占筛选股票" : "占筛选任务";
        const percent = (value, total = stockCount) => {
            if (!total) return 0;
            return Math.max(0, Math.min(100, (Number(value || 0) / total) * 100));
        };
        const setWidth = (id, value) => {
            document.getElementById(id).style.width = `${value.toFixed(1)}%`;
        };
        const setRate = (id, value) => {
            document.getElementById(id).textContent = `${value.toFixed(1)}%`;
        };
        const setCaption = (id) => {
            document.getElementById(id).textContent = returnRateCaption;
        };
        setText("summaryStockCount", data.stock_count);
        setText("summaryCnStockCount", data.cn_stock_count);
        setText("summaryUsStockCount", data.us_stock_count);
        setText("summaryTaskCount", data.task_count);
        setText("summaryReturnGt0", data.return_beats_gt_0);
        setText("summaryReturnGt20", data.return_beats_gt_20);
        setText("summaryReturnGt50", data.return_beats_gt_50);
        setText("summaryReturnGt100", data.return_beats_gt_100);
        setWidth("summaryCnShareBar", percent(cnCount));
        setWidth("summaryUsShareBar", percent(usCount));
        setCaption("summaryReturnGt0Caption");
        setCaption("summaryReturnGt20Caption");
        setCaption("summaryReturnGt50Caption");
        setCaption("summaryReturnGt100Caption");
        const gt0Rate = percent(data.return_beats_gt_0, returnRateBase);
        const gt20Rate = percent(data.return_beats_gt_20, returnRateBase);
        const gt50Rate = percent(data.return_beats_gt_50, returnRateBase);
        const gt100Rate = percent(data.return_beats_gt_100, returnRateBase);
        setWidth("summaryReturnGt0Bar", gt0Rate);
        setWidth("summaryReturnGt20Bar", gt20Rate);
        setWidth("summaryReturnGt50Bar", gt50Rate);
        setWidth("summaryReturnGt100Bar", gt100Rate);
        setRate("summaryReturnGt0Rate", gt0Rate);
        setRate("summaryReturnGt20Rate", gt20Rate);
        setRate("summaryReturnGt50Rate", gt50Rate);
        setRate("summaryReturnGt100Rate", gt100Rate);
    }

    function renderPagination() {
        const start = state.total ? (state.page - 1) * state.perPage + 1 : 0;
        const end = state.total ? Math.min(state.page * state.perPage, state.total) : 0;
        document.getElementById("paginationText").textContent = `显示 ${start}-${end} 条，共 ${state.total} 条任务`;
        document.getElementById("currentPage").textContent = String(state.page);
        document.getElementById("prevPage").disabled = state.page <= 1;
        document.getElementById("nextPage").disabled = state.page >= state.pages;
    }

    async function loadSummary() {
        const bestOnly = document.getElementById("bestOnly").value;
        const stockCode = document.getElementById("stockCode").value.trim();
        if (bestOnly === "false" && !stockCode) {
            throw new Error("查询全部结果时必须输入股票代码、股票名或任务名关键字");
        }
        const queryButton = document.getElementById("queryBtn");
        queryButton.disabled = true;
        queryButton.innerHTML = `<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>查询中`;
        document.getElementById("statusText").textContent = "加载中...";
        try {
            const data = await Api.endpoints.adminModelSummary.summary(collectParams().toString(), {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            const payload = data || {};
            state.columns = payload.columns || [];
            state.total = payload.pagination?.total || 0;
            state.pages = payload.pagination?.pages || 0;
            state.summary = payload.summary || {};
            renderHead();
            renderSummary(state.summary);
            renderBody(payload.items || []);
            renderPagination();
            document.getElementById("statusText").textContent = "已加载";
        } finally {
            queryButton.disabled = false;
            queryButton.innerHTML = `<i class="bi bi-search me-1"></i>查询`;
        }
    }

    function getExportFilenameFromResponse(response) {
        const disposition = response.headers.get("Content-Disposition") || "";
        const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        if (utf8Match) {
            try {
                return decodeURIComponent(utf8Match[1]);
            } catch (error) {
                return utf8Match[1];
            }
        }
        const asciiMatch = disposition.match(/filename="?([^";]+)"?/i);
        return asciiMatch ? asciiMatch[1] : "";
    }

    function openExportCsvModal() {
        const bestOnly = document.getElementById("bestOnly").value;
        const stockCode = document.getElementById("stockCode").value.trim();
        if (bestOnly === "false" && !stockCode) {
            throw new Error("导出全部结果时必须输入股票代码、股票名或任务名关键字");
        }

        const filenameInput = document.getElementById("exportFilename");
        filenameInput.value = defaultExportFilename();
        document.getElementById("exportSummaryText").textContent = describeExportFilters();
        const modalElement = document.getElementById("exportCsvModal");
        const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
        modal.show();
        modalElement.addEventListener("shown.bs.modal", () => {
            filenameInput.focus();
            filenameInput.select();
        }, { once: true });
    }

    async function exportSummaryCsv() {
        const exportButton = document.getElementById("exportCsvBtn");
        const confirmButton = document.getElementById("confirmExportCsvBtn");
        const filename = document.getElementById("exportFilename").value.trim();
        const params = collectParams();
        if (filename) params.set("filename", filename);

        exportButton.disabled = true;
        exportButton.innerHTML = `<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>导出中`;
        confirmButton.disabled = true;
        confirmButton.innerHTML = `<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>导出中`;
        document.getElementById("statusText").textContent = "正在生成 CSV...";
        try {
            const response = await Api.endpoints.export.modelSummaryCsv(params.toString(), {
                headers: { Authorization: `Bearer ${getToken()}` },
            });
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.message || "导出失败");
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = getExportFilenameFromResponse(response) || "model_summary.csv";
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            bootstrap.Modal.getOrCreateInstance(document.getElementById("exportCsvModal")).hide();
            document.getElementById("statusText").textContent = "CSV 已开始下载";
        } finally {
            exportButton.disabled = false;
            exportButton.innerHTML = `<i class="bi bi-file-earmark-spreadsheet"></i>导出 CSV`;
            confirmButton.disabled = false;
            confirmButton.innerHTML = `<i class="bi bi-file-earmark-spreadsheet me-1"></i>确认导出`;
        }
    }

    async function rebuildSummary() {
        const confirmed = confirm("重建索引会在后台扫描历史 task_results，数据量较大时会慢慢跑。是否继续？");
        if (!confirmed) return;
        document.getElementById("statusText").textContent = "正在启动后台重建...";
        const payload = {
            task_type: document.getElementById("taskType").value || undefined,
            task_id: document.getElementById("taskId").value.trim() || undefined,
            batch_size: 20,
            reset: true,
        };
        const data = await Api.endpoints.adminModelSummary.rebuild(payload, {
            headers: { Authorization: `Bearer ${getToken()}` },
        });
        state.rebuildJobId = data.job?.job_id || "";
        renderRebuildTaskLink(data.job);
        document.getElementById("statusText").textContent = `重建任务已创建 ${state.rebuildJobId.slice(0, 8)}`;
        pollRebuildStatus();
    }

    function renderRebuildTaskLink(job) {
        const taskId = job?.task_id || job?.job_id || "";
        const target = document.getElementById("rebuildTaskLink");
        if (!taskId) {
            target.innerHTML = "";
            return;
        }
        target.innerHTML = `<a href="/admin/tasks?keyword=${encodeURIComponent(taskId)}">查看重建任务日志</a>`;
    }

    async function pollRebuildStatus() {
        if (state.rebuildTimer) {
            clearTimeout(state.rebuildTimer);
        }
        if (!state.rebuildJobId) return;
        const params = new URLSearchParams({ job_id: state.rebuildJobId });
        const data = await Api.endpoints.adminModelSummary.rebuildStatus(params.toString(), {
            headers: { Authorization: `Bearer ${getToken()}` },
        });
        const job = data.job;
        if (!job) {
            document.getElementById("statusText").textContent = "暂无重建任务";
            renderRebuildTaskLink(null);
            return;
        }
        renderRebuildTaskLink(job);
        if (job.status === "completed") {
            const result = job.result || {};
            document.getElementById("statusText").textContent = `重建完成：处理 ${result.processed_tasks || 0} 个任务、${result.processed || 0} 条结果，保留 ${result.indexed || 0} 条，去重 ${result.deduped || 0} 条`;
            state.page = 1;
            await loadSummary();
            return;
        }
        if (job.status === "error") {
            document.getElementById("statusText").textContent = job.error || "重建失败";
            return;
        }
        const task = job.task || {};
        const current = task.current_step || 0;
        const total = task.total_steps || 0;
        document.getElementById("statusText").textContent = total ? `后台重建中 ${current}/${total}` : `后台重建中 ${state.rebuildJobId.slice(0, 8)}`;
        state.rebuildTimer = setTimeout(() => {
            pollRebuildStatus().catch((error) => {
                document.getElementById("statusText").textContent = error.message;
            });
        }, 3000);
    }

    function runSummaryQuery() {
        return loadSummary().catch((error) => {
            document.getElementById("statusText").textContent = error.message;
        });
    }

    document.getElementById("filterForm").addEventListener("submit", (event) => {
        event.preventDefault();
        state.page = 1;
        runSummaryQuery();
    });
    document.getElementById("refreshBtn").addEventListener("click", () => runSummaryQuery());
    document.getElementById("exportCsvBtn").addEventListener("click", () => {
        try {
            openExportCsvModal();
        } catch (error) {
            document.getElementById("statusText").textContent = error.message;
            alert(error.message || "导出失败");
        }
    });
    document.getElementById("confirmExportCsvBtn").addEventListener("click", () => exportSummaryCsv().catch((error) => {
        document.getElementById("statusText").textContent = error.message;
        alert(error.message || "导出失败");
    }));
    document.getElementById("rebuildBtn").addEventListener("click", () => rebuildSummary().catch((error) => {
        document.getElementById("statusText").textContent = error.message;
        alert(error.message || "重建失败");
    }));
    document.getElementById("pageSize").addEventListener("change", (event) => {
        state.perPage = Number(event.target.value);
        state.page = 1;
        runSummaryQuery();
    });
    document.getElementById("prevPage").addEventListener("click", () => {
        if (state.page > 1) {
            state.page -= 1;
            runSummaryQuery();
        }
    });
    document.getElementById("nextPage").addEventListener("click", () => {
        if (state.page < state.pages) {
            state.page += 1;
            runSummaryQuery();
        }
    });
    renderHead();
    renderSummary({});
    runSummaryQuery();
