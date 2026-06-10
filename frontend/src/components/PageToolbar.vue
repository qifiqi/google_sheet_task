<template>
  <div class="page-toolbar">
    <div class="page-toolbar__meta">
      <div v-if="eyebrow" class="page-toolbar__eyebrow">{{ eyebrow }}</div>
      <h2 class="page-toolbar__title">{{ title }}</h2>
      <p v-if="description" class="page-toolbar__description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-toolbar__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  eyebrow: { type: String, default: '' },
  title: { type: String, required: true },
  description: { type: String, default: '' },
})
</script>

<style lang="scss" scoped>
.page-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;

  &__meta {
    min-width: 0;
    flex: 1;
  }

  &__eyebrow {
    font-size: var(--app-font-xs);
    font-weight: 500;
    color: var(--app-primary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 2px;
    line-height: 1.4;
  }

  &__title {
    font-size: var(--app-font-xl);
    font-weight: 700;
    color: var(--app-text);
    line-height: 1.3;
    margin: 0;
  }

  &__description {
    font-size: var(--app-font-sm);
    color: var(--app-text-muted);
    margin-top: 4px;
    line-height: 1.5;
  }

  &__actions {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    padding-top: 4px;
  }
}
</style>
