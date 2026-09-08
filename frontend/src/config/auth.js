// 单 Token 子服务模式: 登录发生在主 Web（stock.stplan.cn），
// 本站不提供本地登录页。Token 缺失或失效时统一跳回主 Web 重新登录。
// 可通过 VITE_MAIN_WEB_URL 环境变量覆盖，默认指向主 Web 站点。
export const MAIN_WEB_URL = import.meta.env.VITE_MAIN_WEB_URL || 'http://stock.stplan.cn'

export function goToMainWebLogin() {
  window.location.replace(MAIN_WEB_URL)
}
