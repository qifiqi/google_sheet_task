/**
 * HighPerformanceTable - 高性能虚拟滚动表格组件
 *
 * 特性：
 * - 虚拟滚动：处理百万级数据
 * - 多数据源：流式NDJSON、SSE、直接JSON
 * - 筛选排序：纯前端高性能筛选和排序
 * - CSV导出：支持导出筛选后的数据
 *
 * @example
 * const table = new HighPerformanceTable({
 *   container: '#results-table',
 *   columns: [...],
 *   dataSource: {
 *     type: 'ndjson', // 'ndjson' | 'sse' | 'json'
 *     url: '/api/data',
 *     method: 'POST',
 *     body: {...}
 *   },
 *   virtualScroll: true,
 *   onDataTransform: (item) => ({...item, custom_field: item.a + item.b})
 * });
 */

class HighPerformanceTable {
  constructor(options) {
    this.options = {
      container: null, // 容器选择器或元素
      columns: [], // 列定义
      dataSource: null, // 数据源配置
      virtualScroll: true, // 是否启用虚拟滚动
      visibleRows: 50, // 可见行数
      rowHeight: 40, // 行高（px）
      onDataTransform: null, // 数据转换钩子
      onProgress: null, // 进度回调
      onComplete: null, // 完成回调
      onError: null, // 错误回调
      filters: {}, // 筛选器定义
      sortable: true, // 是否支持排序
      exportable: true, // 是否支持导出
      ...options,
    };

    this.data = []; // 原始数据
    this.filteredData = []; // 筛选后的数据
    this.currentSort = { field: null, direction: null };
    this.scrollTop = 0;
    this.isLoading = false;
    this.abortController = null;

    this.init();
  }

  /**
   * 初始化组件
   */
  init() {
    this.container =
      typeof this.options.container === "string"
        ? document.querySelector(this.options.container)
        : this.options.container;

    if (!this.container) {
      throw new Error("Container not found");
    }

    this.render();
    this.attachEvents();
  }

  /**
   * 渲染表格结构
   */
  render() {
    const html = `
            <div class="hpt-wrapper">
                <div class="hpt-toolbar">
                    <div class="hpt-stats">
                        <span class="hpt-stat hpt-filtered-count">0 条显示</span>
                        <span class="hpt-stat hpt-total-count">0 条总计</span>
                    </div>
                    <div class="hpt-actions">
                        ${this.options.exportable ? '<button class="hpt-btn hpt-export-csv">导出 CSV</button>' : ""}
                    </div>
                </div>
                <div class="hpt-scroll-container" style="max-height: 600px; overflow: auto;">
                    <table class="hpt-table">
                        <thead class="hpt-thead">
                            <tr>
                                ${this.renderHeaders()}
                            </tr>
                        </thead>
                        <tbody class="hpt-tbody"></tbody>
                    </table>
                </div>
                <div class="hpt-progress" style="display: none;">
                    <div class="hpt-progress-bar" style="width: 0%"></div>
                    <div class="hpt-progress-text">加载中...</div>
                </div>
            </div>
        `;

    this.container.innerHTML = html;

    // 缓存DOM引用
    this.dom = {
      wrapper: this.container.querySelector(".hpt-wrapper"),
      toolbar: this.container.querySelector(".hpt-toolbar"),
      scrollContainer: this.container.querySelector(".hpt-scroll-container"),
      table: this.container.querySelector(".hpt-table"),
      thead: this.container.querySelector(".hpt-thead"),
      tbody: this.container.querySelector(".hpt-tbody"),
      progress: this.container.querySelector(".hpt-progress"),
      progressBar: this.container.querySelector(".hpt-progress-bar"),
      progressText: this.container.querySelector(".hpt-progress-text"),
      filteredCount: this.container.querySelector(".hpt-filtered-count"),
      totalCount: this.container.querySelector(".hpt-total-count"),
      exportBtn: this.container.querySelector(".hpt-export-csv"),
    };
  }

  /**
   * 渲染表头
   */
  renderHeaders() {
    return this.options.columns
      .map((col) => {
        const sortable = this.options.sortable && col.sortable !== false;
        const className = sortable ? "hpt-th hpt-sortable" : "hpt-th";
        const icon = sortable ? '<i class="hpt-sort-icon">⇕</i>' : "";

        return `<th class="${className}" data-field="${col.field}">${col.label}${icon}</th>`;
      })
      .join("");
  }

  /**
   * 附加事件监听
   */
  attachEvents() {
    // 虚拟滚动
    if (this.options.virtualScroll) {
      this.dom.scrollContainer.addEventListener(
        "scroll",
        this.debounce(() => {
          this.scrollTop = this.dom.scrollContainer.scrollTop;
          this.renderRows();
        }, 50),
      );
    }

    // 排序
    if (this.options.sortable) {
      this.dom.thead.addEventListener("click", (e) => {
        const th = e.target.closest(".hpt-sortable");
        if (th) {
          const field = th.getAttribute("data-field");
          this.handleSort(field);
        }
      });
    }

    // 导出
    if (this.options.exportable && this.dom.exportBtn) {
      this.dom.exportBtn.addEventListener("click", () => this.exportCSV());
    }
  }

  /**
   * 加载数据
   */
  async load() {
    if (this.isLoading) return;

    this.isLoading = true;
    this.data = [];
    this.filteredData = [];
    this.showProgress(true);

    try {
      const {
        type,
        url,
        method = "POST",
        body,
        headers = {},
      } = this.options.dataSource;

      switch (type) {
        case "ndjson":
          await this.loadNDJSON(url, method, body, headers);
          break;
        case "sse":
          await this.loadSSE(url, method, body, headers);
          break;
        case "json":
          await this.loadJSON(url, method, body, headers);
          break;
        default:
          throw new Error(`Unknown data source type: ${type}`);
      }

      this.filteredData = [...this.data];
      this.renderRows();
      this.updateStats();

      if (this.options.onComplete) {
        this.options.onComplete(this.data);
      }
    } catch (error) {
      if (error.name !== "AbortError") {
        console.error("Load data failed:", error);
        if (this.options.onError) {
          this.options.onError(error);
        }
      }
    } finally {
      this.isLoading = false;
      this.showProgress(false);
    }
  }

  /**
   * 加载 NDJSON 流式数据
   */
  async loadNDJSON(url, method, body, headers) {
    this.abortController = new AbortController();

    const response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: this.abortController.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let count = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (line.trim()) {
          try {
            const item = JSON.parse(line);

            // 检查错误
            if (item.error) {
              throw new Error(item.message || "Server returned error");
            }

            // 数据转换
            const transformed = this.options.onDataTransform
              ? this.options.onDataTransform(item)
              : item;

            this.data.push(transformed);
            count++;

            // 进度回调
            if (count % 100 === 0) {
              this.updateProgress(null, `已接收 ${count} 条数据...`);
              if (this.options.onProgress) {
                this.options.onProgress(count, this.data);
              }
            }
          } catch (err) {
            console.error("Parse JSON failed:", line, err);
            if (err.message.includes("Server returned error")) {
              throw err;
            }
          }
        }
      }
    }

    // 处理剩余数据
    if (buffer.trim()) {
      const item = JSON.parse(buffer);
      if (item.error) {
        throw new Error(item.message || "Server returned error");
      }
      const transformed = this.options.onDataTransform
        ? this.options.onDataTransform(item)
        : item;
      this.data.push(transformed);
    }
  }

  /**
   * 加载 SSE 数据
   */
  async loadSSE(url, method, body, headers) {
    return new Promise((resolve, reject) => {
      const eventSource = new EventSource(url);
      let count = 0;

      eventSource.onmessage = (event) => {
        try {
          const item = JSON.parse(event.data);

          if (item.error) {
            eventSource.close();
            reject(new Error(item.message || "Server returned error"));
            return;
          }

          const transformed = this.options.onDataTransform
            ? this.options.onDataTransform(item)
            : item;

          this.data.push(transformed);
          count++;

          if (count % 100 === 0) {
            this.updateProgress(null, `已接收 ${count} 条数据...`);
            if (this.options.onProgress) {
              this.options.onProgress(count, this.data);
            }
          }
        } catch (err) {
          console.error("Parse SSE data failed:", event.data, err);
        }
      };

      eventSource.onerror = (error) => {
        eventSource.close();
        reject(error);
      };

      eventSource.addEventListener("done", () => {
        eventSource.close();
        resolve();
      });

      this.abortController = {
        abort: () => {
          eventSource.close();
          reject(new Error("AbortError"));
        },
      };
    });
  }

  /**
   * 加载普通 JSON 数据
   */
  async loadJSON(url, method, body, headers) {
    this.abortController = new AbortController();

    const response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: this.abortController.signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const json = await response.json();
    const dataArray = Array.isArray(json) ? json : json.data || [];

    dataArray.forEach((item) => {
      const transformed = this.options.onDataTransform
        ? this.options.onDataTransform(item)
        : item;
      this.data.push(transformed);
    });

    this.updateProgress(100, `加载完成，共 ${this.data.length} 条`);
  }

  /**
   * 渲染表格行（支持虚拟滚动）
   */
  renderRows() {
    const fragment = document.createDocumentFragment();

    if (
      this.options.virtualScroll &&
      this.filteredData.length > this.options.visibleRows
    ) {
      // 虚拟滚动模式
      const startIdx = Math.floor(this.scrollTop / this.options.rowHeight);
      const endIdx = Math.min(
        startIdx + this.options.visibleRows,
        this.filteredData.length,
      );

      // 顶部占位
      if (startIdx > 0) {
        const spacer = document.createElement("tr");
        spacer.style.height = startIdx * this.options.rowHeight + "px";
        spacer.className = "hpt-spacer";
        fragment.appendChild(spacer);
      }

      // 可见行
      for (let i = startIdx; i < endIdx; i++) {
        const tr = this.createRow(this.filteredData[i], i);
        fragment.appendChild(tr);
      }

      // 底部占位
      if (endIdx < this.filteredData.length) {
        const spacer = document.createElement("tr");
        spacer.style.height =
          (this.filteredData.length - endIdx) * this.options.rowHeight + "px";
        spacer.className = "hpt-spacer";
        fragment.appendChild(spacer);
      }
    } else {
      // 普通模式
      this.filteredData.forEach((item, idx) => {
        const tr = this.createRow(item, idx);
        fragment.appendChild(tr);
      });
    }

    this.dom.tbody.innerHTML = "";
    this.dom.tbody.appendChild(fragment);
  }

  /**
   * 创建表格行
   */
  createRow(item, index) {
    const tr = document.createElement("tr");
    tr.className = "hpt-tr";
    tr.style.height = this.options.rowHeight + "px";

    const cells = this.options.columns.map((col) => {
      const value = col.render
        ? col.render(item, index)
        : this.getNestedValue(item, col.field);

      return `<td class="hpt-td">${this.escapeHtml(value)}</td>`;
    });

    tr.innerHTML = cells.join("");
    return tr;
  }

  /**
   * 应用筛选
   */
  applyFilter(filterFn) {
    if (typeof filterFn === "function") {
      this.filteredData = this.data.filter(filterFn);
    } else {
      this.filteredData = [...this.data];
    }

    this.scrollTop = 0;
    this.dom.scrollContainer.scrollTop = 0;
    this.renderRows();
    this.updateStats();
  }

  /**
   * 排序
   */
  handleSort(field) {
    const column = this.options.columns.find((col) => col.field === field);
    if (!column) return;

    // 三态排序
    if (this.currentSort.field === field) {
      if (this.currentSort.direction === "asc") {
        this.currentSort.direction = "desc";
      } else if (this.currentSort.direction === "desc") {
        this.currentSort.direction = null;
        this.currentSort.field = null;
      }
    } else {
      this.currentSort.field = field;
      this.currentSort.direction = "asc";
    }

    // 更新图标
    this.updateSortIcons();

    // 执行排序
    if (this.currentSort.field && this.currentSort.direction) {
      this.filteredData.sort((a, b) => {
        let aVal = this.getNestedValue(a, field);
        let bVal = this.getNestedValue(b, field);

        if (column.sortComparator) {
          return column.sortComparator(aVal, bVal, this.currentSort.direction);
        }

        // 默认排序
        if (aVal == null) aVal = -Infinity;
        if (bVal == null) bVal = -Infinity;

        return this.currentSort.direction === "asc" ? aVal - bVal : bVal - aVal;
      });
    } else {
      // 恢复原始顺序
      this.applyFilter(null);
      return;
    }

    this.renderRows();
  }

  /**
   * 更新排序图标
   */
  updateSortIcons() {
    this.dom.thead.querySelectorAll(".hpt-sortable").forEach((th) => {
      const icon = th.querySelector(".hpt-sort-icon");
      const field = th.getAttribute("data-field");

      if (field === this.currentSort.field) {
        icon.textContent = this.currentSort.direction === "asc" ? "↑" : "↓";
      } else {
        icon.textContent = "⇕";
      }
    });
  }

  /**
   * 导出 CSV
   */
  exportCSV() {
    const headers = this.options.columns.map((col) => col.label);
    const rows = [headers.join(",")];

    this.filteredData.forEach((item) => {
      const values = this.options.columns.map((col) => {
        const value =
          col.render && col.exportRaw
            ? this.getNestedValue(item, col.field)
            : col.render
              ? col.render(item)
              : this.getNestedValue(item, col.field);

        return this.escapeCsvValue(value);
      });
      rows.push(values.join(","));
    });

    const csv = "﻿" + rows.join("\n"); // UTF-8 BOM
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `export_${Date.now()}.csv`;
    link.click();

    URL.revokeObjectURL(url);
  }

  /**
   * 取消加载
   */
  abort() {
    if (this.abortController) {
      this.abortController.abort();
    }
  }

  /**
   * 显示/隐藏进度条
   */
  showProgress(show) {
    this.dom.progress.style.display = show ? "block" : "none";
  }

  /**
   * 更新进度
   */
  updateProgress(percentage, message) {
    if (percentage !== null && percentage !== undefined) {
      this.dom.progressBar.style.width = percentage + "%";
    }
    if (message) {
      this.dom.progressText.textContent = message;
    }
  }

  /**
   * 更新统计信息
   */
  updateStats() {
    this.dom.filteredCount.textContent = `${this.filteredData.length} 条显示`;
    this.dom.totalCount.textContent = `${this.data.length} 条总计`;
  }

  /**
   * 获取嵌套属性值
   */
  getNestedValue(obj, path) {
    return path.split(".").reduce((acc, part) => acc?.[part], obj);
  }

  /**
   * 转义 HTML
   */
  escapeHtml(str) {
    if (str == null) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  /**
   * 转义 CSV 值
   */
  escapeCsvValue(value) {
    if (value == null) return "";
    const str = String(value);
    if (str.includes(",") || str.includes('"') || str.includes("\n")) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  }

  /**
   * 防抖
   */
  debounce(func, wait) {
    let timeout;
    return function (...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  }

  /**
   * 销毁组件
   */
  destroy() {
    this.abort();
    if (this.container) {
      this.container.innerHTML = "";
    }
  }
}

// 导出
if (typeof module !== "undefined" && module.exports) {
  module.exports = HighPerformanceTable;
}
if (typeof window !== "undefined") {
  window.HighPerformanceTable = HighPerformanceTable;
}
