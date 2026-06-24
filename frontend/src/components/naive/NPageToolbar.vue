<template>
  <div class="n-page-toolbar">
    <div class="n-page-toolbar__meta">
      <span class="n-page-toolbar__eyebrow">{{ eyebrow }}</span>
      <h2 class="n-page-toolbar__title">{{ title }}</h2>
      <p v-if="description" class="n-page-toolbar__desc">{{ description }}</p>
    </div>
    <div class="n-page-toolbar__actions">
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

<style scoped>
.n-page-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.n-page-toolbar__meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.n-page-toolbar__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #6366f1;
}

.n-page-toolbar__title {
  margin: 0;
  font-size: clamp(1.5rem, 1.2rem + 0.8vw, 2rem);
  font-weight: 700;
  color: #f1f5f9;
  line-height: 1.2;
}

.n-page-toolbar__desc {
  margin: 2px 0 0;
  font-size: 13px;
  color: #94a3b8;
}

.n-page-toolbar__actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
