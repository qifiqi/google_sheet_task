import { ref } from 'vue'
import { searchStocks } from '@/api/backtest'

/**
 * Stock search composable with debounce and result caching.
 * @param {object} [options]
 * @param {number} [options.delay=300] - Debounce delay in ms
 * @param {string} [options.market] - Market filter ('cn' | 'en')
 */
export function useStockSearch({ delay = 300, market = '' } = {}) {
  const query = ref('')
  const results = ref([])
  const loading = ref(false)

  let timer = null
  const cache = new Map()

  function search(keyword) {
    query.value = keyword ?? ''
    const q = query.value.trim()

    if (!q) {
      results.value = []
      return
    }

    const cacheKey = `${market}:${q}`
    if (cache.has(cacheKey)) {
      results.value = cache.get(cacheKey)
      return
    }

    if (timer) clearTimeout(timer)
    timer = setTimeout(async () => {
      loading.value = true
      try {
        const params = { q, market }
        Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })
        const res = await searchStocks(params)
        const data = Array.isArray(res) ? res : (res.data || res.results || [])
        cache.set(cacheKey, data)
        results.value = data
      } catch {
        results.value = []
      } finally {
        loading.value = false
      }
    }, delay)
  }

  function clearCache() {
    cache.clear()
  }

  return { query, results, loading, search, clearCache }
}
