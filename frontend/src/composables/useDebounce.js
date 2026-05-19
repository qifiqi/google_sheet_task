import { ref } from 'vue'

/**
 * Debounce a value or function call.
 * @param {number} delay - Debounce delay in ms (default 300)
 */
export function useDebounce(delay = 300) {
  let timer = null

  function debounce(fn) {
    if (timer) clearTimeout(timer)
    timer = setTimeout(fn, delay)
  }

  function cancel() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  return { debounce, cancel }
}

/**
 * Create a debounced ref that updates after a delay.
 * @param {any} initialValue
 * @param {number} delay
 */
export function useDebouncedRef(initialValue, delay = 300) {
  const value = ref(initialValue)
  const debouncedValue = ref(initialValue)
  let timer = null

  function update(newVal) {
    value.value = newVal
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      debouncedValue.value = newVal
    }, delay)
  }

  return { value, debouncedValue, update }
}
