let xlsxJsStylePromise = null

// 与 useChartJs 相同的按需 CDN 加载策略：xlsx-js-style 只在真正导出时注入一次。
export function useXlsxJsStyle() {
  function loadXlsxJsStyle() {
    if (typeof window === 'undefined') {
      return Promise.reject(new Error('xlsx-js-style requires a browser environment'))
    }

    if (window.XLSX) {
      return Promise.resolve(window.XLSX)
    }

    if (!xlsxJsStylePromise) {
      xlsxJsStylePromise = new Promise((resolve, reject) => {
        const existing = document.querySelector('script[data-xlsx-js-style-loader="true"]')

        if (existing) {
          existing.addEventListener('load', () => resolve(window.XLSX), { once: true })
          existing.addEventListener('error', reject, { once: true })
          return
        }

        const script = document.createElement('script')
        script.src = 'https://cdn.jsdelivr.net/npm/xlsx-js-style@1.2.0/dist/xlsx.bundle.js'
        script.dataset.xlsxJsStyleLoader = 'true'
        script.onload = () => resolve(window.XLSX)
        script.onerror = reject
        document.head.appendChild(script)
      }).catch((error) => {
        xlsxJsStylePromise = null
        throw error
      })
    }

    return xlsxJsStylePromise
  }

  return {
    loadXlsxJsStyle,
  }
}
