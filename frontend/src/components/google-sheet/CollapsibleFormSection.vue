<script setup lang="ts">
import { shallowRef, watch } from 'vue'

const props = defineProps<{
  contentId: string
  title: string
  subtitle: string
  summary?: string
}>()

const expanded = defineModel<boolean>({ required: true })
const mountedOnce = shallowRef(expanded.value)

watch(expanded, (value) => {
  if (value) mountedOnce.value = true
})

function toggle() {
  expanded.value = !expanded.value
}
</script>

<template>
  <section class="collapsible-form-section">
    <header class="collapsible-form-section__header">
      <button
        type="button"
        class="collapsible-form-section__trigger"
        :aria-controls="props.contentId"
        :aria-expanded="expanded"
        :aria-label="`${expanded ? '折叠' : '展开'}${props.title}`"
        @click="toggle"
      >
        <span class="collapsible-form-section__title">{{ props.title }}</span>
        <span class="collapsible-form-section__subtitle">{{ expanded ? props.subtitle : props.summary || props.subtitle }}</span>
      </button>
      <div v-if="$slots.actions" class="collapsible-form-section__actions">
        <slot name="actions" />
      </div>
    </header>
    <div v-if="mountedOnce" v-show="expanded" :id="props.contentId" class="collapsible-form-section__content">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.collapsible-form-section {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface);
}

.collapsible-form-section__header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
}

.collapsible-form-section__trigger {
  display: grid;
  min-width: 0;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.collapsible-form-section__trigger:hover .collapsible-form-section__title {
  color: var(--admin-primary);
}

.collapsible-form-section__trigger:focus-visible {
  outline: 2px solid var(--admin-primary);
  outline-offset: 4px;
}

.collapsible-form-section__title {
  color: var(--admin-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  transition: color 180ms ease;
}

.collapsible-form-section__subtitle {
  margin-top: 4px;
  color: var(--admin-text-muted);
  font-size: 13px;
  line-height: 20px;
}

.collapsible-form-section__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: end;
  gap: 8px;
}

.collapsible-form-section__content {
  display: grid;
  min-width: 0;
  gap: 16px;
  margin-top: 16px;
}

@media (max-width: 640px) {
  .collapsible-form-section {
    padding: 16px;
  }

  .collapsible-form-section__header {
    align-items: stretch;
    flex-direction: column;
  }

  .collapsible-form-section__actions {
    justify-content: stretch;
  }
}

@media (prefers-reduced-motion: reduce) {
  .collapsible-form-section__title {
    transition: none;
  }
}
</style>
