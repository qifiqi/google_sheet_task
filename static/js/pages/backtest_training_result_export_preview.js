
    const RESULT_ID = (window.location.pathname.match(/\/result\/(\d+)/) || [])[1] || '';
    let exportRows = [];
    let exportFilename = '';

    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('backToResultLink').href = buildResultHref();
        document.getElementById('copyAllButton').addEventListener('click', copyAllRows);
        document.getElementById('downloadButton').addEventListener('click', downloadCsv);
        loadPreview();
    });

    function buildResultHref() {
        const currentParams = new URLSearchParams(window.location.search);
        const resultParams = new URLSearchParams();
        ['list_page', 'list_per_page', 'result_page', 'result_per_page'].forEach((key) => {
            const value = currentParams.get(key);
            if (value) {
                resultParams.set(key, value);
            }
        });
        const query = resultParams.toString();
        return `/backtest-training/result/${encodeURIComponent(RESULT_ID)}${query ? `?${query}` : ''}`;
    }

    function setStatus(message) {
        document.getElementById('previewStatus').textContent = message;
    }

    async function loadPreview() {
        const grid = document.getElementById('previewGrid');
        try {
            const payload = await Api.endpoints.backtest.taskResultExportPreview(encodeURIComponent(RESULT_ID));

            exportRows = Array.isArray(payload.rows) ? payload.rows : [];
            exportFilename = payload.filename || `backtest_result_${RESULT_ID}_details.csv`;
            document.getElementById('previewFilename').textContent = exportFilename;
            document.getElementById('copyAllButton').disabled = !exportRows.length;
            document.getElementById('downloadButton').disabled = !exportRows.length;
            renderRows(grid, exportRows);
            setStatus(`已加载 ${exportRows.length} 行导出内容`);
        } catch (error) {
            grid.innerHTML = '';
            const message = document.createElement('div');
            message.className = 'export-preview-empty text-danger';
            message.textContent = error.message || '加载失败';
            grid.appendChild(message);
            setStatus(message.textContent);
        }
    }

    function renderRows(grid, rows) {
        grid.innerHTML = '';
        const table = document.createElement('table');
        table.className = 'table table-bordered export-preview-table';
        table.setAttribute('aria-label', 'CSV 导出内容');
        const caption = document.createElement('caption');
        caption.className = 'visually-hidden';
        caption.textContent = '当前回测结果的 CSV 导出内容';
        table.appendChild(caption);
        const tbody = document.createElement('tbody');
        const fragment = document.createDocumentFragment();

        rows.forEach((row) => {
            const tr = document.createElement('tr');
            row.forEach((value) => {
                const td = document.createElement('td');
                td.textContent = value == null ? '' : String(value);
                tr.appendChild(td);
            });
            fragment.appendChild(tr);
        });
        tbody.appendChild(fragment);
        table.appendChild(tbody);
        grid.appendChild(table);
    }

    function buildClipboardText() {
        return exportRows.map((row) => row.map((value) => value == null ? '' : String(value)).join('\t')).join('\n');
    }

    async function copyAllRows() {
        const text = buildClipboardText();
        if (!text) {
            setStatus('暂无可复制内容');
            return;
        }

        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.setAttribute('readonly', '');
                textarea.style.position = 'fixed';
                textarea.style.left = '-9999px';
                document.body.appendChild(textarea);
                textarea.select();
                const copied = document.execCommand('copy');
                textarea.remove();
                if (!copied) {
                    throw new Error('复制失败');
                }
            }
            setStatus('已复制全部内容，可直接粘贴到 WPS 或 Excel');
        } catch (error) {
            setStatus(`复制失败：${error.message || '未知错误'}`);
        }
    }

    async function downloadCsv() {
        const button = document.getElementById('downloadButton');
        button.disabled = true;
        try {
            const response = await Api.endpoints.export.backtestResult(encodeURIComponent(RESULT_ID));
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.message || '下载失败');
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = exportFilename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            setStatus('已开始下载 CSV 文件');
        } catch (error) {
            setStatus(`下载失败：${error.message || '未知错误'}`);
        } finally {
            button.disabled = !exportRows.length;
        }
    }
