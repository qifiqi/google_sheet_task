// 返回导航兜底（"返回"统一语义：回来源页，无来源时落兜底路由）。
// 站内进入时 vue-router 4 会在 history.state 写入 back（来源路由 fullPath），
// 此时 router.back() 原样回到来源页并保留其状态；新标签页直开 / 刷新落地的
// 首个页面没有 back，router.back() 会毫无反应，此时改 push 兜底路由，
// 保证"返回"永远落到一个真实页面。
// fallback 兜底路由：字符串，或 () => string（兜底目标依赖运行时状态时传函数）。
import { useRouter } from 'vue-router'

export function useBackNavigation(fallback) {
  const router = useRouter()
  return () => {
    if (window.history.state && window.history.state.back != null) {
      router.back()
    } else {
      router.push(typeof fallback === 'function' ? fallback() : fallback)
    }
  }
}
