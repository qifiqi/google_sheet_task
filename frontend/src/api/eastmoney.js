// 东方财富行情访问层。
// K 线接口后端暂无同源代理，沿用页面直连行情站点的 JSONP 方式；
// 股票搜索统一走后端 /api/search-stocks，前端不再单独维护一份搜索调用。
import { searchStocks } from './backtest'

const KLINE_URL = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
const KLINE_UT = 'b5d7eb2120497da188fdebb62aeffaf6'
const SEARCH_PAGE_SIZE = 20

let jsonpSeq = 0

// 极简 JSONP：动态 script + 一次性全局回调，超时或加载失败统一 reject。
function jsonp(url, params, timeout = 15000) {
  return new Promise((resolve, reject) => {
    const callbackName = `__eastmoneyJsonp_${Date.now()}_${jsonpSeq++}`
    const query = new URLSearchParams({ ...params, cb: callbackName, _: String(Date.now()) })
    const script = document.createElement('script')
    let settled = false
    let timer = null

    const settle = (fn, value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      delete window[callbackName]
      script.remove()
      fn(value)
    }

    timer = setTimeout(() => settle(reject, new Error('行情接口请求超时')), timeout)
    window[callbackName] = (data) => settle(resolve, data)
    script.onerror = () => settle(reject, new Error('行情接口网络请求失败'))
    script.src = `${url}?${query.toString()}`
    document.head.appendChild(script)
  })
}

// 拉取K线。query 需要 secid/klt/lmt/fqt，字段清单与桌面端行情接口一致。
export function fetchEastmoneyKlines(query) {
  return jsonp(KLINE_URL, {
    fields1: 'f1,f2,f3,f4,f5,f6',
    fields2: 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
    ut: KLINE_UT,
    secid: query.secid,
    dect: '1',
    klt: query.klt,
    lmt: query.lmt,
    fqt: query.fqt,
    forcect: '1',
    end: '20500101',
  })
}

// 后端搜索返回项目统一代码（如 600519.SS / 0700.HK），K 线 secid 需要东财
// 原生无后缀代码；港股统一代码会去掉前导零，这里按东财规则补回 5 位。
function toSecid(code, market) {
  const marketId = market === undefined || market === null ? '' : String(market).trim()
  let base = String(code || '').trim()
  const suffixIndex = base.indexOf('.')
  if (suffixIndex > 0) {
    base = base.slice(0, suffixIndex)
  }
  if (marketId === '116') {
    base = base.padStart(5, '0')
  }
  if (!/^\d+$/.test(marketId) || !base) {
    return ''
  }
  return `${marketId}.${base}`
}

// 股票搜索：返回候选列表（secid/code/name/market/displayName）。
export async function searchSecurities(keyword) {
  const data = await searchStocks({ q: keyword, page_size: SEARCH_PAGE_SIZE })
  const items = Array.isArray(data?.results) ? data.results : []
  return items
    .map((item) => {
      const secid = toSecid(item?.code, item?.market)
      if (!secid) {
        return null
      }
      const code = secid.split('.')[1]
      const name = String(item?.name || '')
      return {
        secid,
        code,
        name,
        market: String(item?.market ?? '').trim(),
        displayName: code + (name ? ` | ${name}` : ''),
      }
    })
    .filter(Boolean)
}
