import { onMounted, onUnmounted } from 'vue'

export function usePolling(task, options = {}) {
  const {
    interval = 30000,
    immediate = true,
    isActive = () => true,
  } = options

  let timer = null
  let inFlight = false

  async function tick() {
    if (inFlight || typeof document !== 'undefined' && document.hidden) {
      return
    }

    if (!isActive()) {
      return
    }

    inFlight = true

    try {
      await task()
    } finally {
      inFlight = false
    }
  }

  function start() {
    if (timer) {
      return
    }

    if (immediate) {
      void tick()
    }

    timer = window.setInterval(() => {
      void tick()
    }, interval)
  }

  function stop() {
    if (timer) {
      window.clearInterval(timer)
      timer = null
    }
  }

  function handleVisibilityChange() {
    if (!document.hidden) {
      void tick()
    }
  }

  onMounted(() => {
    start()

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange)
    }
  })

  onUnmounted(() => {
    stop()

    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  })

  return {
    start,
    stop,
    tick,
  }
}
