<template>
  <div class="page-toolbar">
    <div class="page-toolbar__meta">
      <div v-if="eyebrow" class="page-toolbar__eyebrow">{{ eyebrow }}</div>
      <h2 class="page-title">{{ title }}</h2>
      <p v-if="description" class="page-description">{{ description }}</p>
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
