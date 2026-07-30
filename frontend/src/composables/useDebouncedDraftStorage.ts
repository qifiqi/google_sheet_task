import { onBeforeUnmount, watch, type Ref } from 'vue'

export function useDebouncedDraftStorage<T extends object>(
  draft: T,
  storedDraft: Ref<T>,
  clone: (value: T) => T,
  delay = 400,
) {
  let timer: number | undefined

  watch(draft, () => {
    window.clearTimeout(timer)
    timer = window.setTimeout(() => {
      storedDraft.value = clone(draft)
    }, delay)
  }, { deep: true })

  onBeforeUnmount(() => window.clearTimeout(timer))
}
