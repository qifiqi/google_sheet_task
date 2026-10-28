// Weight Combination Analysis Page with Tabulator
(function() {
    'use strict';

    let table = null;
    let allData = [];
    let isAnalyzing = false;
    let abortController = null;

    // 当前筛选值缓存：field -> { min, max }
    // 弹窗打开时回填用户输入的值；按钮激活态也由此判断
    const headerFilterValues = {};

    // 表头筛选控件：field -> { btn: 漏斗按钮, success: Tabulator 应用筛选回调 }
    // 编辑器在 clearHeaderFilter 后会被 Tabulator 重建，此表随编辑器初始化刷新
    const filterControls = {};

    // 筛选弹窗（懒创建，挂在 body 下 fixed 定位）
    let filterPopup = null;
    let filterPopupCtx = null; // { field, title, btn }

    function hasActiveRangeFilter(field) {
        const v = headerFilterValues[field];
        return !!(v && ((v.min !== null && v.min !== undefined) || (v.max !== null && v.max !== undefined)));
    }

    function setFilterButtonIcon(btn, active) {
        btn.classList.toggle('is-active', active);
        btn.innerHTML = `<i class="bi bi-funnel${active ? '-fill' : ''}"></i>`;
    }

    function refreshFilterButton(field) {
        const ctrl = filterControls[field];
        if (ctrl && ctrl.btn) setFilterButtonIcon(ctrl.btn, hasActiveRangeFilter(field));
    }

    // ============ 范围筛选：漏斗按钮编辑器（点击弹出筛选弹窗） ============
    function filterButtonEditor(column, onRendered, success, cancel, editorParams) {
        // 注意：Tabulator 表头筛选编辑器的第一个参数不是完整 Cell/Column 组件，
        // 只有 getField/getColumn/getElement 等方法，列标题须经 getColumn().getDefinition() 获取
        const field = column.getField();
        const colComp = column.getColumn ? column.getColumn() : null;
        const title = (colComp && colComp.getDefinition ? colComp.getDefinition().title : null) || field;

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'wc-filter-btn';
        btn.title = '范围筛选';
        btn.setAttribute('aria-label', `范围筛选：${title}`);
        setFilterButtonIcon(btn, hasActiveRangeFilter(field));

        btn.addEventListener('click', function(e) {
            // 阻止冒泡到列头，避免误触发排序；stopImmediatePropagation 连同
            // Tabulator 在同一元素上附加的 focus 抢占监听一并拦下
            e.stopPropagation();
            e.preventDefault();
            e.stopImmediatePropagation();
            toggleFilterPopup(field, title, btn);
        });

        filterControls[field] = { btn: btn, success: success };
        return btn;
    }

    // ============ 范围筛选弹窗 ============
    function getPopupInputs() {
        return {
            min: filterPopup.querySelector('[data-role="min"]'),
            max: filterPopup.querySelector('[data-role="max"]')
        };
    }

    function ensureFilterPopup() {
        if (filterPopup) return filterPopup;

        filterPopup = document.createElement('div');
        filterPopup.className = 'wc-filter-popup';
        filterPopup.setAttribute('role', 'dialog');
        filterPopup.setAttribute('aria-label', '范围筛选');
        filterPopup.innerHTML = `
            <div class="wc-filter-popup__header">
                <span class="wc-filter-popup__title"></span>
                <button type="button" class="wc-filter-popup__close" aria-label="关闭"><i class="bi bi-x-lg"></i></button>
            </div>
            <div class="wc-filter-popup__body">
                <div class="wc-filter-popup__field">
                    <label for="wc-filter-min">最小值</label>
                    <input type="number" id="wc-filter-min" class="form-control form-control-sm wc-filter-popup__input" data-role="min" placeholder="不限">
                </div>
                <div class="wc-filter-popup__field">
                    <label for="wc-filter-max">最大值</label>
                    <input type="number" id="wc-filter-max" class="form-control form-control-sm wc-filter-popup__input" data-role="max" placeholder="不限">
                </div>
                <p class="wc-filter-popup__hint">最小值不能大于最大值</p>
            </div>
            <div class="wc-filter-popup__footer">
                <button type="button" class="btn btn-sm btn-outline-secondary" data-role="clear">
                    <i class="bi bi-x-circle me-1"></i>清除
                </button>
                <button type="button" class="btn btn-sm btn-primary" data-role="apply">
                    <i class="bi bi-check-lg me-1"></i>应用
                </button>
            </div>`;
        document.body.appendChild(filterPopup);

        filterPopup.querySelector('.wc-filter-popup__close').addEventListener('click', closeFilterPopup);
        filterPopup.querySelector('[data-role="clear"]').addEventListener('click', clearRangeFilter);
        filterPopup.querySelector('[data-role="apply"]').addEventListener('click', applyRangeFilter);

        const inputs = getPopupInputs();
        [inputs.min, inputs.max].forEach(function(input) {
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') applyRangeFilter();
                if (e.key === 'Escape') closeFilterPopup();
            });
        });

        // 点击弹窗与漏斗按钮之外的区域关闭
        document.addEventListener('mousedown', function(e) {
            if (!filterPopup.classList.contains('show')) return;
            if (filterPopup.contains(e.target)) return;
            if (filterPopupCtx && filterPopupCtx.btn.contains(e.target)) return;
            closeFilterPopup();
        });
        // 页面/表格滚动、窗口缩放时关闭，避免弹窗飘离锚点
        window.addEventListener('resize', closeFilterPopup);
        window.addEventListener('scroll', closeFilterPopup, true);

        return filterPopup;
    }

    function toggleFilterPopup(field, title, btn) {
        if (filterPopupCtx && filterPopupCtx.field === field && filterPopup.classList.contains('show')) {
            closeFilterPopup();
            return;
        }
        openFilterPopup(field, title, btn);
    }

    function openFilterPopup(field, title, btn) {
        ensureFilterPopup();
        filterPopupCtx = { field: field, title: title, btn: btn };

        filterPopup.querySelector('.wc-filter-popup__title').textContent = title;
        filterPopup.querySelector('.wc-filter-popup__hint').classList.remove('is-visible');

        const inputs = getPopupInputs();
        const v = headerFilterValues[field] || {};
        inputs.min.value = v.min !== null && v.min !== undefined ? v.min : '';
        inputs.max.value = v.max !== null && v.max !== undefined ? v.max : '';
        inputs.min.classList.remove('is-invalid');
        inputs.max.classList.remove('is-invalid');

        filterPopup.classList.add('show');
        positionFilterPopup(btn);
        // Tabulator 会在同一点击事件里把焦点抢回按钮，延迟聚焦保证输入框拿到焦点
        setTimeout(function() { inputs.min.focus(); }, 0);
    }

    function positionFilterPopup(btn) {
        const rect = btn.getBoundingClientRect();
        const pw = filterPopup.offsetWidth;
        const ph = filterPopup.offsetHeight;

        let left = rect.right - pw; // 默认右对齐到按钮
        left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));

        let top = rect.bottom + 6;
        if (top + ph > window.innerHeight - 8) {
            top = rect.top - ph - 6; // 下方空间不足时弹到按钮上方
        }

        filterPopup.style.left = left + 'px';
        filterPopup.style.top = Math.max(8, top) + 'px';
    }

    function closeFilterPopup() {
        if (!filterPopup) return;
        filterPopup.classList.remove('show');
        filterPopupCtx = null;
    }

    function updateStats() {
        setStats(table.getDataCount('active'), allData.length);
    }

    function setStats(filteredCount, totalCount) {
        const filteredEl = document.getElementById('filtered-count');
        const totalEl = document.getElementById('total-count');
        if (filteredEl) filteredEl.textContent = `${filteredCount} 条显示`;
        if (totalEl) totalEl.textContent = `${totalCount} 条总计`;
    }

    // Tabulator 的 refreshData 管线分帧异步提交 activeRows，事件派发瞬间计数可能还是旧值；
    // 从下一帧起持续刷新统计，直到计数稳定
    function refreshStatsDeferred() {
        let last = null;
        let ticks = 0;
        const tick = function() {
            const active = table.getDataCount('active');
            if (active !== last) {
                last = active;
                setStats(active, allData.length);
            }
            if (++ticks < 15) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    }

    function applyRangeFilter() {
        if (!filterPopupCtx) return;
        const field = filterPopupCtx.field;
        const inputs = getPopupInputs();
        const minRaw = inputs.min.value.trim();
        const maxRaw = inputs.max.value.trim();
        const min = minRaw === '' ? null : parseFloat(minRaw);
        const max = maxRaw === '' ? null : parseFloat(maxRaw);

        if (min !== null && max !== null && min > max) {
            inputs.min.classList.add('is-invalid');
            inputs.max.classList.add('is-invalid');
            filterPopup.querySelector('.wc-filter-popup__hint').classList.add('is-visible');
            return;
        }

        headerFilterValues[field] = { min: min, max: max };
        const ctrl = filterControls[field];
        if (ctrl) ctrl.success(headerFilterValues[field]);
        refreshFilterButton(field);
        refreshStatsDeferred();
        closeFilterPopup();
    }

    function clearRangeFilter() {
        if (!filterPopupCtx) return;
        const field = filterPopupCtx.field;
        const inputs = getPopupInputs();
        inputs.min.value = '';
        inputs.max.value = '';
        inputs.min.classList.remove('is-invalid');
        inputs.max.classList.remove('is-invalid');

        headerFilterValues[field] = { min: null, max: null };
        const ctrl = filterControls[field];
        if (ctrl) ctrl.success({ min: null, max: null });
        refreshFilterButton(field);
        refreshStatsDeferred();
        closeFilterPopup();
    }

    // ============ 自定义范围筛选函数 ============
    function minMaxFilterFunction(headerValue, rowValue, rowData, filterParams) {
        if (!headerValue || (headerValue.min === null && headerValue.max === null)) {
            return true;
        }

        // 空值放行
        if (rowValue === null || rowValue === undefined || rowValue === '') {
            return true;
        }

        const value = parseFloat(rowValue);
        if (isNaN(value)) {
            return true;
        }

        if (headerValue.min !== null && headerValue.min !== undefined && value < headerValue.min) {
            return false;
        }

        if (headerValue.max !== null && headerValue.max !== undefined && value > headerValue.max) {
            return false;
        }

        return true;
    }

    // ============ 列工厂 ============
    function numberFormatter(digits, suffix = '') {
        return function(cell) {
            const val = cell.getValue();
            return val != null && val !== '' ? Number(val).toFixed(digits) + suffix : '-';
        };
    }

    function rangeColumn(title, field, opts = {}) {
        const digits = opts.digits ?? 2;
        const suffix = opts.suffix || '';
        const width = opts.width || 160;

        return {
            title: title,
            field: field,
            width: width,
            sorter: 'number',
            headerFilter: filterButtonEditor,
            headerFilterFunc: minMaxFilterFunction,
            headerTooltip: true,
            formatter: numberFormatter(digits, suffix)
        };
    }

    // DOM elements
    const form = document.getElementById('weight-combination-form');
    const taskIdInput = document.getElementById('task-id');
    const stepInput = document.getElementById('step');
    const maxWeightInput = document.getElementById('max-weight');
    const minWeightInput = document.getElementById('min-weight');
    const singleCapInput = document.getElementById('single-cap');
    const numProductsInput = document.getElementById('num-products');
    const btnAnalyze = document.getElementById('btn-analyze');
    const btnCancel = document.getElementById('btn-cancel');
    const progressCard = document.getElementById('progress-card');
    const progressBar = document.getElementById('progress-bar');
    const progressInfo = document.getElementById('progress-info');
    const resultsCard = document.getElementById('results-card');

    // 产品选择 + 单股范围面板（任务 ID 填好后自动加载）
    const productsPanel = document.getElementById('products-panel');
    const productsTbody = document.getElementById('products-tbody');
    const productsTableWrap = document.getElementById('products-table-wrap');
    const productsMessage = document.getElementById('products-message');
    const productsSummary = document.getElementById('products-summary');
    const productsSelectAll = document.getElementById('products-select-all');
    const btnReloadProducts = document.getElementById('btn-reload-products');
    const btnResetRanges = document.getElementById('btn-reset-ranges');
    const btnPinRatios = document.getElementById('btn-pin-ratios');
    const productsStepHint = document.getElementById('products-step-hint');

    // 面板状态：每项对应一个 TaskResult。多参数方案任务里同一股票会出现多次，
    // 提交时按 result_id 回传，服务端据此精确对应到枚举中的产品。
    let products = [];
    let productsTaskId = '';       // 已成功加载面板的任务 ID（用于跳过重复请求）
    let productsLoadSeq = 0;       // 请求序号：旧响应回来时直接丢弃
    let productsAbort = null;      // 切换任务时中止上一次加载
    let productsLoading = false;   // 面板加载中：此时提交会带上一个任务的产品与范围

    // Initialize
    document.addEventListener('DOMContentLoaded', function() {
        setupEventListeners();
        initializeTable();
        prefillTaskIdFromUrl();
    });

    function setupEventListeners() {
        form.addEventListener('submit', handleAnalyze);
        btnCancel.addEventListener('click', handleCancel);
        // 任务 ID 失焦/回车后加载产品列表；同一任务已加载过则不重复请求
        taskIdInput.addEventListener('change', function() {
            const taskId = taskIdInput.value.trim();
            if (taskId && taskId === productsTaskId) return;
            loadProducts(taskId);
        });
        // 步长边输边同步提示（范围须为步长整数倍，用户改步长后据此校验/重置）
        stepInput.addEventListener('input', updateStepHint);
        productsSelectAll.addEventListener('change', toggleAllProducts);
        btnReloadProducts.addEventListener('click', function() {
            loadProducts(taskIdInput.value.trim());
        });
        btnResetRanges.addEventListener('click', function() {
            applyDefaultRanges();
            renderProducts();
        });
        btnPinRatios.addEventListener('click', function() {
            pinProductRatios();
            renderProducts();
        });
    }

    function prefillTaskIdFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const taskId = params.get('task_id');
        if (taskId) {
            taskIdInput.value = taskId;
            loadProducts(taskId);
        }
    }

    // ============ 产品选择 + 单股范围 ============
    function productLabel(product) {
        return product.stock_name || product.stock_code || ('结果 ' + product.result_id);
    }

    function readStep() {
        const step = parseInt(stepInput.value, 10);
        return Number.isInteger(step) && step > 0 ? step : 5;
    }

    function formatRatioText(value) {
        if (value === null || value === undefined) return '-';
        return (Math.round(value * 100) / 100) + '%';
    }

    function parseRatioText(raw) {
        if (raw === null || raw === undefined || raw === '') return null;
        const value = parseFloat(raw);
        return Number.isFinite(value) ? value : null;
    }

    // 默认单股上限 = 任务配置比例（无配置比例时回退到「单股上限」输入框），
    // 按步长向下取整：既保证"0 ~ 配置比例"的语义，也不会因取整超过配置比例。
    function defaultMaxRatio(product, step) {
        let base = product.ratioNum;
        if (base === null) {
            const fallback = parseInt(singleCapInput.value, 10);
            base = Number.isInteger(fallback) ? fallback : 100;
        }
        const capped = Math.max(0, Math.min(base, 100));
        return Math.floor(capped / step) * step;
    }

    function applyDefaultRanges() {
        const step = readStep();
        products.forEach(function(product) {
            product.min = 0;
            product.max = defaultMaxRatio(product, step);
        });
    }

    // 把已勾选且配置比例>0 的产品固定为配置比例（按步长向下取整）：min=max ⇒
    // 权重恒定、不按步长漫游，且下限>0 使其成为"固定产品"（不计入组合产品数）。
    // 其余产品保持 0 ~ 上限，继续参与"组合产品数"的子集枚举。
    function pinProductRatios() {
        const step = readStep();
        products.forEach(function(product) {
            if (!product.usable || !product.checked) return;
            if (product.ratioNum === null || product.ratioNum === undefined) return;
            const pinned = Math.floor(Math.max(0, Math.min(product.ratioNum, 100)) / step) * step;
            if (pinned <= 0) return;
            product.min = pinned;
            product.max = pinned;
        });
    }

    function updateStepHint() {
        productsStepHint.textContent = String(readStep());
    }

    function updateProductsSummary() {
        const usable = products.filter(function(product) { return product.usable; });
        const selected = usable.filter(function(product) { return product.checked; });
        const ratioSum = selected.reduce(function(sum, product) {
            return sum + (product.ratioNum || 0);
        }, 0);

        if (!usable.length) {
            productsSummary.textContent = products.length ? '没有可用于组合的产品' : '暂无产品';
        } else {
            productsSummary.textContent = `已选 ${selected.length} / 共 ${usable.length}` +
                (ratioSum > 0 ? `（所选配置比例合计 ${formatRatioText(ratioSum)}）` : '');
        }

        productsSelectAll.disabled = !usable.length;
        productsSelectAll.checked = usable.length > 0 && selected.length === usable.length;
        productsSelectAll.indeterminate = selected.length > 0 && selected.length < usable.length;
    }

    function showProductsMessage(text, level) {
        productsMessage.textContent = text;
        productsMessage.className = 'wc-products__message small text-' + (level || 'muted');
        productsMessage.style.display = 'block';
    }

    function hideProductsMessage() {
        productsMessage.style.display = 'none';
    }

    function updateProductRowState(product) {
        const enabled = product.usable && product.checked;
        if (product.minEl) product.minEl.disabled = !enabled;
        if (product.maxEl) product.maxEl.disabled = !enabled;
        if (product.fixedEl) product.fixedEl.disabled = !enabled;
        if (product.rowEl) product.rowEl.classList.toggle('wc-products__row--off', !enabled);
    }

    function makeRangeInput(product, key) {
        const input = document.createElement('input');
        input.type = 'number';
        input.className = 'form-control form-control-sm wc-products__input';
        input.min = '0';
        input.max = '100';
        input.step = '1';
        input.value = String(product[key]);
        input.setAttribute('aria-label', (key === 'min' ? '单股下限 ' : '单股上限 ') + productLabel(product));
        input.addEventListener('input', function() {
            product[key] = input.value.trim() === '' ? '' : Number(input.value);
            input.classList.remove('is-invalid');
        });
        return input;
    }

    function renderProducts() {
        productsTbody.innerHTML = '';
        products.forEach(function(product) {
            const row = document.createElement('tr');

            const selectCell = document.createElement('td');
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'form-check-input';
            checkbox.checked = product.checked;
            checkbox.disabled = !product.usable;
            checkbox.setAttribute('aria-label', '选择 ' + productLabel(product));
            if (!product.usable) {
                checkbox.title = '该产品没有可用的收益序列，无法参与组合';
            }
            checkbox.addEventListener('change', function() {
                product.checked = checkbox.checked;
                // 行取消勾选时连带取消必选，避免残留不可达的必选标记
                if (!product.checked) {
                    product.fixed = false;
                    if (product.fixedEl) product.fixedEl.checked = false;
                }
                updateProductRowState(product);
                updateProductsSummary();
            });
            selectCell.appendChild(checkbox);

            const fixedCell = document.createElement('td');
            const fixedCheckbox = document.createElement('input');
            fixedCheckbox.type = 'checkbox';
            fixedCheckbox.className = 'form-check-input';
            fixedCheckbox.checked = !!product.fixed;
            fixedCheckbox.disabled = !product.usable || !product.checked;
            fixedCheckbox.title = '勾选后恒定持仓，不计入组合产品数';
            fixedCheckbox.setAttribute('aria-label', '必选 ' + productLabel(product));
            fixedCheckbox.addEventListener('change', function() {
                product.fixed = fixedCheckbox.checked;
            });
            fixedCell.appendChild(fixedCheckbox);

            const nameCell = document.createElement('td');
            const nameEl = document.createElement('div');
            nameEl.className = 'wc-products__name';
            nameEl.textContent = product.stock_name || product.stock_code || 'N/A';
            const codeEl = document.createElement('div');
            codeEl.className = 'wc-products__code text-muted';
            codeEl.textContent = product.stock_code || '';
            nameCell.appendChild(nameEl);
            nameCell.appendChild(codeEl);

            const ratioCell = document.createElement('td');
            ratioCell.className = 'wc-products__ratio';
            ratioCell.textContent = formatRatioText(product.ratioNum);

            const minCell = document.createElement('td');
            const minInput = makeRangeInput(product, 'min');
            minCell.appendChild(minInput);

            const maxCell = document.createElement('td');
            const maxInput = makeRangeInput(product, 'max');
            maxCell.appendChild(maxInput);

            row.appendChild(selectCell);
            row.appendChild(fixedCell);
            row.appendChild(nameCell);
            row.appendChild(ratioCell);
            row.appendChild(minCell);
            row.appendChild(maxCell);
            productsTbody.appendChild(row);

            product.rowEl = row;
            product.minEl = minInput;
            product.maxEl = maxInput;
            product.fixedEl = fixedCheckbox;
            updateProductRowState(product);
        });
        updateProductsSummary();
    }

    function toggleAllProducts() {
        const checked = productsSelectAll.checked;
        products.forEach(function(product) {
            if (product.usable) product.checked = checked;
        });
        renderProducts();
    }

    // 分析进行中时整体禁用面板，避免结果与参数不一致
    function setProductsBusy(busy) {
        productsPanel.querySelectorAll('input, button').forEach(function(el) {
            el.disabled = busy;
        });
        if (!busy) {
            products.forEach(updateProductRowState);
            updateProductsSummary();
        }
    }

    async function loadProducts(taskId) {
        productsTaskId = '';
        if (productsAbort) {
            productsAbort.abort();
            productsAbort = null;
        }
        if (!taskId) {
            products = [];
            productsLoading = false;
            productsPanel.style.display = 'none';
            return;
        }

        const seq = ++productsLoadSeq;
        productsAbort = new AbortController();
        // 任务 ID 变更由输入框失焦（change）触发，紧接着的提交仍会读到上一个任务的
        // products；标记加载中，让 handleAnalyze 拒绝这次提交而不是发错范围。
        productsLoading = true;
        productsPanel.style.display = 'block';
        productsTableWrap.style.display = 'none';
        productsSelectAll.checked = false;
        productsSelectAll.indeterminate = false;
        productsSelectAll.disabled = true;
        productsSummary.textContent = '';
        showProductsMessage('正在加载产品列表...', 'muted');

        try {
            const data = await Api.endpoints.performanceAnalysis.weightCombinationProducts(taskId, {
                signal: productsAbort.signal
            });
            if (seq !== productsLoadSeq) return;

            const list = (data && data.products) || [];
            products = list.map(function(item) {
                const ratioNum = parseRatioText(item.ratio);
                return {
                    result_id: item.result_id,
                    product_index: item.product_index,
                    stock_code: item.stock_code,
                    stock_name: item.stock_name,
                    ratioNum: ratioNum,
                    ratioText: formatRatioText(ratioNum),
                    usable: !!item.has_returns,
                    // 已配置比例为 0 的产品在组合里本就不参与，默认不勾选（可手动勾选后改上限）
                    checked: !!item.has_returns && ratioNum !== 0,
                    // 必选：恒定持仓，不计入组合产品数
                    fixed: false,
                    min: 0,
                    max: 0
                };
            });
            applyDefaultRanges();
            renderProducts();
            productsTaskId = taskId;
            productsTableWrap.style.display = products.length ? 'block' : 'none';

            if (!products.length) {
                showProductsMessage('该任务没有成功的结果，无法进行权重组合分析。', 'danger');
            } else if (!products.some(function(product) { return product.usable; })) {
                showProductsMessage('该任务的成功结果都没有可用的收益序列，无法进行权重组合分析。', 'danger');
            } else {
                hideProductsMessage();
            }
        } catch (error) {
            if (error.name === 'AbortError') return;
            if (seq !== productsLoadSeq) return;
            products = [];
            productsTableWrap.style.display = 'none';
            updateProductsSummary();
            showProductsMessage('产品列表加载失败：' + error.message, 'danger');
        } finally {
            if (seq === productsLoadSeq) {
                productsAbort = null;
                productsLoading = false;
            }
        }
    }

    // 校验面板选择并生成请求字段；面板未加载（无产品）时返回空载荷，
    // 请求退化为原有的"全部产品 + 全局单股上限"语义。
    function collectProductSelection() {
        if (!products.length) return { error: null, payload: {} };

        const step = readStep();
        const selected = products.filter(function(product) {
            return product.usable && product.checked;
        });
        if (!selected.length) return { error: '请至少选择一个参与组合的产品' };

        const ranges = [];
        for (let i = 0; i < selected.length; i++) {
            const product = selected[i];
            const label = productLabel(product);
            const invalid = function(message) {
                if (product.minEl) product.minEl.classList.add('is-invalid');
                if (product.maxEl) product.maxEl.classList.add('is-invalid');
                return { error: `「${label}」${message}` };
            };

            if (product.min === '' || product.max === '' ||
                !Number.isInteger(product.min) || !Number.isInteger(product.max)) {
                return invalid('的单股下限/上限必须是整数');
            }
            if (product.min < 0 || product.max > 100 || product.min > product.max) {
                return invalid('的单股范围必须满足 0 ≤ 下限 ≤ 上限 ≤ 100');
            }
            if (product.min % step !== 0 || product.max % step !== 0) {
                return invalid(`的单股范围必须是步长 ${step}% 的整数倍（可点「重置范围」按配置比例重算）`);
            }
            if (product.fixed && product.max <= 0) {
                return invalid('勾了必选，单股上限必须大于 0（持仓 = 权重 > 0）');
            }
            ranges.push({
                result_id: product.result_id,
                min_weight: product.min,
                max_weight: product.max
            });
        }

        const payload = {
            result_ids: selected.map(function(product) { return product.result_id; }),
            stock_ranges: ranges
        };

        // 必选产品：恒定持仓，不计入组合产品数
        const fixedIds = selected
            .filter(function(product) { return product.fixed; })
            .map(function(product) { return product.result_id; });
        if (fixedIds.length) payload.fixed_result_ids = fixedIds;

        // 组合产品数（不含必选产品）；留空表示不限
        const numProducts = parseInt(numProductsInput.value, 10);
        if (Number.isInteger(numProducts)) {
            if (numProducts < 0 || numProducts > 100) {
                return { error: '组合产品数必须在 0-100 之间（留空表示不限）' };
            }
            const freeCount = selected.length - fixedIds.length;
            if (numProducts > freeCount) {
                return { error: `组合产品数不能超过可变产品数 ${freeCount}（必选产品不计入）` };
            }
            payload.num_products = numProducts;
        }

        return { error: null, payload: payload };
    }

    /**
     * 初始化 Tabulator 表格
     */
    function initializeTable() {
        table = new Tabulator('#results-table', {
            height: '600px',
            layout: 'fitColumns',
            placeholder: '暂无数据，请先进行分析',
            pagination: false,
            virtualDom: true,
            virtualDomBuffer: 300,
            // 股票组合一行一只，行高随内容增长
            variableHeight: true,

            columns: [
                {
                    title: '#',
                    formatter: 'rownum',
                    width: 60,
                    hozAlign: 'center',
                    headerSort: false
                },
                {
                    title: '股票组合',
                    field: 'stocks_display',
                    minWidth: 240,
                    headerSort: false,
                    formatter: 'textarea',
                    tooltip: true
                },
                rangeColumn('年化收益率(指数)', 'index_rate_disp', { width: 185, digits: 2, suffix: '%' }),
                rangeColumn('年化收益率(策略)', 'start_rate_disp', { width: 185, digits: 2, suffix: '%' }),
                rangeColumn('最大回撤(指数)', 'index_dd_disp', { width: 175, digits: 2, suffix: '%' }),
                rangeColumn('最大回撤(策略)', 'start_dd_disp', { width: 175, digits: 2, suffix: '%' }),
                rangeColumn('权重和(%)', 'weight_sum', { width: 140, digits: 0, suffix: '%' }),
                {
                    title: '查看',
                    field: 'view_action',
                    width: 80,
                    hozAlign: 'center',
                    headerSort: false,
                    cssClass: 'view-action-col',
                    formatter: viewActionFormatter
                }
            ],

            initialSort: [],
            // 列较多，窄屏时横向滚动；不用 collapse（会把末列折叠进行内展开区，反而难读）
            responsiveLayout: false,

            renderComplete: function() {
                updateStats();
            }
        });

        // ✅ 不再设置默认筛选，加载后显示全部数据

        table.on('dataFiltered', function() {
            updateStats();
        });

        document.getElementById('export-excel-btn').onclick = exportExcel;
        document.getElementById('clear-filter-btn').onclick = function() {
            closeFilterPopup();
            Object.keys(headerFilterValues).forEach(k => delete headerFilterValues[k]);
            table.clearHeaderFilter();
            // clearHeaderFilter 会重建编辑器，这里兜底刷新一遍按钮激活态
            Object.keys(filterControls).forEach(refreshFilterButton);
            refreshStatsDeferred();
        };
    }

    /**
     * 处理分析表单提交
     */
    async function handleAnalyze(e) {
        e.preventDefault();
        if (isAnalyzing) return;

        const taskId = taskIdInput.value.trim();
        if (!taskId) {
            alert('请输入任务 ID');
            return;
        }
        // 面板尚在加载上一个任务的产品与范围，此时提交会把旧范围发给新任务
        if (productsLoading) {
            alert('产品列表加载中，请稍候再试');
            return;
        }

        const step = parseInt(stepInput.value);
        const maxWeight = parseInt(maxWeightInput.value);
        const minWeight = parseInt(minWeightInput.value);
        const singleCap = parseInt(singleCapInput.value);

        if (step < 1 || step > 100) { alert('权重步长必须在 1-100 之间'); return; }
        if (100 % step !== 0) { alert('权重步长必须能整除 100'); return; }
        if (maxWeight < 1 || maxWeight > 100) { alert('组合总权重上限必须在 1-100 之间'); return; }
        if (minWeight < 0 || minWeight > 100) { alert('组合总权重下限必须在 0-100 之间'); return; }
        if (minWeight > maxWeight) { alert('组合总权重下限不能大于上限'); return; }

        const selection = collectProductSelection();
        if (selection.error) { alert(selection.error); return; }
        const useRanges = !!(selection.payload && selection.payload.stock_ranges);

        // 单股上限只在未启用单股范围时生效，启用后不再校验它的网格约束（服务端同样忽略）
        if (!useRanges) {
            if (singleCap < 1 || singleCap > 100) { alert('单只股票权重上限必须在 1-100 之间'); return; }
            if (maxWeight % step !== 0 || minWeight % step !== 0 || singleCap % step !== 0) {
                alert('所有权重参数必须是步长的整数倍');
                return;
            }
            if (singleCap < step) { alert('单只股票权重上限不能小于步长'); return; }
        } else if (maxWeight % step !== 0 || minWeight % step !== 0) {
            alert('组合总权重上下限必须是步长的整数倍');
            return;
        }

        const payload = {
            task_id: taskId,
            step: step,
            max_weight: maxWeight,
            min_weight: minWeight
        };
        Object.assign(payload, selection.payload);
        // 启用单股范围后不发送 single_cap：服务端此时不读它，但它的字段级范围约束
        // （>0、≤100）仍会生效，会让一个不生效的值卡住请求。
        if (!useRanges) payload.single_cap = singleCap;
        startAnalysis(payload);
    }

    /**
     * 开始分析
     */
    async function startAnalysis(payload) {
        isAnalyzing = true;
        allData = [];

        btnAnalyze.disabled = true;
        btnCancel.style.display = 'inline-block';
        progressCard.style.display = 'block';
        resultsCard.style.display = 'none';
        setProductsBusy(true);

        // 清空数据 + 筛选缓存
        closeFilterPopup();
        Object.keys(headerFilterValues).forEach(k => delete headerFilterValues[k]);
        table.clearData();
        table.clearHeaderFilter();

        updateProgress(0, '正在发送请求...');

        try {
            abortController = new AbortController();

            const response = await fetch('/api/performance-analysis/weight-combination', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: abortController.signal
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || `请求失败: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let processedCount = 0;
            let renderedCount = 0;

            updateProgress(0, '正在接收数据...');

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.trim()) {
                        try {
                            const data = JSON.parse(line);
                            if (data.error) throw new Error(data.message || '服务端返回错误');

                            const transformed = transformData(data);
                            allData.push(transformed);
                            processedCount++;

                            if (processedCount % 20 === 0) {
                                updateProgress(null, `已接收 ${processedCount} 条组合...`);

                                const newRows = allData.slice(renderedCount);
                                if (renderedCount === 0) {
                                    table.setData(allData);
                                    resultsCard.style.display = 'block';
                                } else if (newRows.length) {
                                    table.addData(newRows);
                                }
                                renderedCount = allData.length;
                            }
                        } catch (err) {
                            console.error('解析 JSON 失败:', line, err);
                            if (err.message.includes('服务端返回错误')) throw err;
                        }
                    }
                }
            }

            if (buffer.trim()) {
                try {
                    const data = JSON.parse(buffer);
                    if (data.error) throw new Error(data.message || '服务端返回错误');
                    const transformed = transformData(data);
                    allData.push(transformed);
                    processedCount++;
                } catch (err) {
                    console.error('解析最后的 JSON 失败:', buffer, err);
                    if (err.message.includes('服务端返回错误')) throw err;
                }
            }

            // 最终补差量
            const finalNewRows = allData.slice(renderedCount);
            if (finalNewRows.length) {
                if (renderedCount === 0) {
                    table.setData(allData);
                } else {
                    table.addData(finalNewRows);
                }
                renderedCount = allData.length;
            } else {
                table.setData(allData);
            }

            updateProgress(100, `分析完成！共生成 ${allData.length} 个组合`);
            resultsCard.style.display = 'block';

            // ✅ 只更新统计，不再应用默认筛选
            setTimeout(function() {
                updateStats();
            }, 0);

            setTimeout(() => {
                progressCard.style.display = 'none';
            }, 2000);

        } catch (error) {
            if (error.name === 'AbortError') {
                updateProgress(0, '分析已取消');
                setTimeout(() => {
                    progressCard.style.display = 'none';
                }, 1500);
            } else {
                console.error('分析失败:', error);
                alert('分析失败: ' + error.message);
                updateProgress(0, '分析失败');
            }
        } finally {
            isAnalyzing = false;
            btnAnalyze.disabled = false;
            btnCancel.style.display = 'none';
            setProductsBusy(false);
            abortController = null;
        }
    }

    /**
     * 数据转换：生成 *_disp 字段（原始值 × 100）
     */
    function transformData(item) {
        item.weight_sum = item.stocks.reduce((sum, stock) => sum + stock.ratio, 0);

        const indexRate = item.annualized_rates?.index;
        const startRate = item.annualized_rates?.start;
        const indexDd = item.year_max_drawdown?.index;
        const startDd = item.year_max_drawdown?.start;

        item.index_rate = indexRate;
        item.start_rate = startRate;
        item.index_dd = indexDd;
        item.start_dd = startDd;

        item.index_rate_disp = indexRate != null ? Number(indexRate) * 100 : null;
        item.start_rate_disp = startRate != null ? Number(startRate) * 100 : null;
        item.index_dd_disp = indexDd != null ? Number(indexDd) * 100 : null;
        item.start_dd_disp = startDd != null ? Number(startDd) * 100 : null;

        // 一行一只股票（textarea formatter 保留换行），替代挤成一团的长串
        item.stocks_display = item.stocks
            .filter(s => s.ratio > 0)
            .map(s => `${s.stock_name || s.stock_code || 'N/A'} ${s.ratio}%`)
            .join('\n');

        return item;
    }

    // ============ 查看列：携带组合比例跳转全局预览 ============
    function viewActionFormatter(cell) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-sm btn-outline-primary';
        btn.title = '携带该组合比例打开全局预览';
        btn.innerHTML = '<i class="bi bi-eye me-1"></i>查看';
        btn.addEventListener('click', function() {
            openGlobalPreviewWithRatios(cell.getRow().getData());
        });
        return btn;
    }

    function openGlobalPreviewWithRatios(rowData) {
        const taskId = taskIdInput.value.trim();
        if (!taskId) {
            alert('缺少任务 ID，无法跳转全局预览');
            return;
        }
        const ratios = (rowData.stocks || [])
            .filter(function(stock) { return stock && stock.stock_code && Number(stock.ratio) > 0; })
            .map(function(stock) { return { stock_code: stock.stock_code, ratio: Number(stock.ratio) }; });
        if (!ratios.length) {
            alert('该组合没有可用的股票比例');
            return;
        }
        // 新标签打开，保留当前页分析结果
        const params = new URLSearchParams({ ratios: JSON.stringify(ratios) });
        window.open('/backtest-multi-product/global-preview/' + encodeURIComponent(taskId) + '?' + params.toString(), '_blank');
    }

    function handleCancel() {
        if (abortController) abortController.abort();
    }

    function updateProgress(percentage, message) {
        if (percentage !== null) {
            progressBar.style.width = percentage + '%';
            progressBar.setAttribute('aria-valuenow', percentage);
            progressBar.textContent = percentage + '%';
        }
        if (message) progressInfo.textContent = message;
    }

    // ============ 导出 Excel（SheetJS 懒加载复用 Biz.returnSeriesExport） ============
    // 各股票权重拆列承载组合构成，不再导出「股票组合」文本列；
    // 指标与权重均写入内置百分比数字格式（0.00% / 0%）——单元格仍是数值，可筛选可排序。
    async function exportExcel() {
        if (!allData.length) {
            alert('暂无数据，请先进行分析');
            return;
        }
        // 与页面筛选/排序保持一致：只导出当前 active 行
        const rows = table.getData('active');
        if (!rows.length) {
            alert('当前筛选条件下没有可导出的数据');
            return;
        }

        try {
            await Biz.returnSeriesExport.ensureSheetJs();

            // 股票拆列：按当前行序里首次出现的顺序，列头 = 股票名（缺省用代码）
            const stockCols = [];
            const seenKeys = new Set();
            rows.forEach(function(row) {
                (row.stocks || []).forEach(function(stock) {
                    const key = stock.stock_code || stock.stock_name;
                    if (!key || seenKeys.has(key)) return;
                    seenKeys.add(key);
                    stockCols.push({ key: key, label: stock.stock_name || stock.stock_code || 'N/A' });
                });
            });

            // 百分比统一写成小数 + 数字格式，避免拼 "%" 字符串破坏数值类型
            const frac = function(value, digits) {
                return (value === null || value === undefined) ? '' : Number((value / 100).toFixed(digits));
            };
            const header = [
                '#',
                '年化收益率(指数)',
                '年化收益率(策略)',
                '最大回撤(指数)',
                '最大回撤(策略)',
                ...stockCols.map(function(col) { return col.label; }),
                '权重和'
            ];

            const aoa = [header];
            rows.forEach(function(row, index) {
                const ratioByKey = {};
                (row.stocks || []).forEach(function(stock) {
                    const key = stock.stock_code || stock.stock_name;
                    if (key && !(key in ratioByKey)) ratioByKey[key] = stock.ratio;
                });
                aoa.push([
                    index + 1,
                    frac(row.index_rate_disp, 4),
                    frac(row.start_rate_disp, 4),
                    frac(row.index_dd_disp, 4),
                    frac(row.start_dd_disp, 4),
                    ...stockCols.map(function(col) {
                        const ratio = ratioByKey[col.key];
                        return ratio > 0 ? Number((ratio / 100).toFixed(4)) : '';
                    }),
                    frac(row.weight_sum, 4)
                ]);
            });

            const sheet = XLSX.utils.aoa_to_sheet(aoa);
            // 列序：#(0)、指标(1-4)、各股票权重、权重和
            const stockStart = 5;
            const weightCol = stockStart + stockCols.length;
            const setFormat = function(rowIdx, colIdx, fmt) {
                const addr = XLSX.utils.encode_cell({ r: rowIdx, c: colIdx });
                const cell = sheet[addr];
                if (cell && typeof cell.v === 'number') cell.z = fmt;
            };
            for (let r = 1; r < aoa.length; r++) {
                for (let c = 1; c <= 4; c++) setFormat(r, c, '0.00%');
                for (let c = stockStart; c < weightCol; c++) setFormat(r, c, '0%');
                setFormat(r, weightCol, '0%');
            }
            sheet['!cols'] = [
                { wch: 5 },
                { wch: 16 },
                { wch: 16 },
                { wch: 16 },
                { wch: 16 },
                ...stockCols.map(function() { return { wch: 20 }; }),
                { wch: 10 }
            ];
            const workbook = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(workbook, sheet, '权重组合');
            // 页面无任务名/K线区间，按命名规范回落：类型默认词 + 导出时间。
            XLSX.writeFile(workbook, buildExportFilename('权重组合'), { compression: true });
        } catch (error) {
            console.error('导出 Excel 失败:', error);
            alert('导出 Excel 失败: ' + error.message);
        }
    }

})();