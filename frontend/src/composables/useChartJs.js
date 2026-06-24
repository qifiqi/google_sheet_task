let chartJsPromise = null

export function useChartJs() {
  function loadChartJs() {
    if (typeof window === 'undefined') {
      return Promise.reject(new Error('Chart.js requires a browser environment'))
    }

    if (window.Chart) {
      return Promise.resolve(window.Chart)
    }

    if (!chartJsPromise) {
      chartJsPromise = new Promise((resolve, reject) => {
        const existing = document.querySelector('script[data-chartjs-loader="true"]')

        if (existing) {
          existing.addEventListener('load', () => resolve(window.Chart), { once: true })
          existing.addEventListener('error', reject, { once: true })
          return
        }

        const script = document.createElement('script')
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'
        script.dataset.chartjsLoader = 'true'
        script.onload = () => resolve(window.Chart)
        script.onerror = reject
        document.head.appendChild(script)
      }).catch((error) => {
        chartJsPromise = null
        throw error
      })
    }

    return chartJsPromise
  }

  return {
    loadChartJs,
  }
}
