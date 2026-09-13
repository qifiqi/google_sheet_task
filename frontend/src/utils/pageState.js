// 列表↔详情↔结果↔全局预览 的分页状态传递链（自静态版 backtest_*_list/detail.js 翻译）。
// 约定与静态版逐键一致：
// - 列表自身：URL 带 page/per_page，并落 localStorage <prefix>:list_pagination；
// - 详情回列表：带 page/per_page 还原列表页码；
// - 详情/结果/全局预览互跳：统一携带 list_page/list_per_page/result_page/result_per_page 四参；
// - 结果分页：URL result_page/result_per_page > 每任务 localStorage <prefix>:task_results:<taskId>:pagination > 默认。

export function parsePositiveInt(value, fallback = 1) {
  const n = parseInt(value, 10)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

export function readJsonStorage(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || '{}') || {}
  } catch {
    return {}
  }
}

export function writeJsonStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {}
}

// 列表初始分页：URL page/per_page > localStorage > 默认
export function initialListPagination(query, storageKey, defaultPerPage = 20) {
  const stored = readJsonStorage(storageKey)
  return {
    page: parsePositiveInt(query?.page, parsePositiveInt(stored.page, 1)),
    perPage: parsePositiveInt(query?.per_page, parsePositiveInt(stored.per_page, defaultPerPage)),
  }
}

// 详情页从导航参数还原来源列表的分页（回列表时用）
export function listQueryFromRoute(query, storageKey, defaultPerPage = 20) {
  const stored = readJsonStorage(storageKey)
  return {
    page: parsePositiveInt(query?.list_page, parsePositiveInt(stored.page, 1)),
    perPage: parsePositiveInt(query?.list_per_page, parsePositiveInt(stored.per_page, defaultPerPage)),
  }
}

// 结果分页初始值
export function initialResultPagination(query, storageKey, defaultPerPage = 10) {
  const stored = readJsonStorage(storageKey)
  return {
    page: parsePositiveInt(query?.result_page, parsePositiveInt(stored.page, 1)),
    perPage: parsePositiveInt(query?.result_per_page, parsePositiveInt(stored.per_page, defaultPerPage)),
  }
}

// 结果页/全局预览互跳统一携带的四参
export function paginationLinkQuery(listState, resultState) {
  return {
    list_page: String(listState.page),
    list_per_page: String(listState.perPage),
    result_page: String(resultState?.page ?? 1),
    result_per_page: String(resultState?.perPage ?? 10),
  }
}

const PAGING_KEYS = ['list_page', 'list_per_page', 'result_page', 'result_per_page']

// 结果/预览页原样透传收到的分页参数（buildResultHref 语义）
export function pickPagingQuery(query) {
  const out = {}
  PAGING_KEYS.forEach((key) => {
    if (query?.[key] != null) out[key] = String(query[key])
  })
  return out
}

// replaceState 语义：同步分页参数进当前 URL，不触发组件重载/重新取数
export function replaceQuery(router, route, extra = {}) {
  router.replace({ query: { ...route.query, ...extra } }).catch(() => {})
}
