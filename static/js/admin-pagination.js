(function () {
    function normalizePagination(pagination, currentPage) {
        const data = pagination || {};
        const page = Number(data.page || currentPage || 1);
        const perPage = Number(data.per_page || data.perPage || 20);
        const total = Number(data.total || 0);
        const pages = Number(data.pages || Math.ceil(total / Math.max(perPage, 1)) || 0);
        return {
            page,
            perPage,
            total,
            pages,
            hasPrev: Boolean(data.has_prev ?? data.hasPrev ?? page > 1),
            hasNext: Boolean(data.has_next ?? data.hasNext ?? page < pages),
        };
    }

    function visiblePages(page, pages, maxVisiblePages) {
        if (pages <= 0) {
            return [];
        }
        const maxPages = Math.max(3, Number(maxVisiblePages || 7));
        let start = Math.max(1, page - Math.floor(maxPages / 2));
        let end = Math.min(pages, start + maxPages - 1);
        if (end - start + 1 < maxPages) {
            start = Math.max(1, end - maxPages + 1);
        }
        const result = [];
        for (let value = start; value <= end; value += 1) {
            result.push(value);
        }
        return result;
    }

    function setInfo(infoElement, pagination, noun) {
        if (!infoElement) {
            return;
        }
        if (!pagination.total) {
            infoElement.textContent = "暂无数据";
            return;
        }
        const start = (pagination.page - 1) * pagination.perPage + 1;
        const end = Math.min(pagination.page * pagination.perPage, pagination.total);
        infoElement.textContent = `显示第 ${start}-${end} 条，共 ${pagination.total} 条${noun || ""}`;
    }

    function buttonMarkup(label, page, disabled, active, ariaLabel) {
        const activeClass = active ? " active" : "";
        const disabledClass = disabled ? " disabled" : "";
        const disabledAttr = disabled ? " disabled" : "";
        const ariaCurrent = active ? ' aria-current="page"' : "";
        return `
            <li class="page-item${activeClass}${disabledClass}">
                <button class="page-link" type="button" data-page="${page}" aria-label="${ariaLabel || label}"${ariaCurrent}${disabledAttr}>${label}</button>
            </li>
        `;
    }

    function render(options) {
        const paginationElement = document.getElementById(options.paginationId);
        const infoElement = document.getElementById(options.infoId);
        if (!paginationElement) {
            return;
        }

        const pagination = normalizePagination(options.pagination, options.currentPage);
        setInfo(infoElement, pagination, options.noun);
        paginationElement.innerHTML = "";

        if (pagination.pages <= 1) {
            return;
        }

        paginationElement.insertAdjacentHTML(
            "beforeend",
            buttonMarkup("上一页", pagination.page - 1, !pagination.hasPrev, false, "上一页"),
        );

        const pages = visiblePages(pagination.page, pagination.pages, options.maxVisiblePages);
        if (pages[0] > 1) {
            paginationElement.insertAdjacentHTML("beforeend", buttonMarkup("1", 1, false, pagination.page === 1, "第 1 页"));
            if (pages[0] > 2) {
                paginationElement.insertAdjacentHTML("beforeend", '<li class="page-item disabled"><span class="page-link">...</span></li>');
            }
        }

        pages.forEach((pageNumber) => {
            paginationElement.insertAdjacentHTML(
                "beforeend",
                buttonMarkup(String(pageNumber), pageNumber, false, pageNumber === pagination.page, `第 ${pageNumber} 页`),
            );
        });

        const lastVisible = pages[pages.length - 1] || 0;
        if (lastVisible < pagination.pages) {
            if (lastVisible < pagination.pages - 1) {
                paginationElement.insertAdjacentHTML("beforeend", '<li class="page-item disabled"><span class="page-link">...</span></li>');
            }
            paginationElement.insertAdjacentHTML(
                "beforeend",
                buttonMarkup(String(pagination.pages), pagination.pages, false, pagination.page === pagination.pages, `第 ${pagination.pages} 页`),
            );
        }

        paginationElement.insertAdjacentHTML(
            "beforeend",
            buttonMarkup("下一页", pagination.page + 1, !pagination.hasNext, false, "下一页"),
        );

        paginationElement.querySelectorAll("[data-page]").forEach((button) => {
            button.addEventListener("click", () => {
                const nextPage = Number(button.dataset.page || 1);
                if (button.disabled || nextPage === pagination.page) {
                    return;
                }
                if (typeof options.onPageChange === "function") {
                    options.onPageChange(nextPage);
                }
            });
        });
    }

    window.AdminPagination = { render };
})();
